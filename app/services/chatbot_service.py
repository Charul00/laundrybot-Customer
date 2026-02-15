"""
Intent router + booking flow. Booking steps: name → address → phone → delivery → service → weight → pickup → instructions → payment → create.
Handles: /start, book, track, pricing, support, and natural-language order queries.
Payment: COD, UPI, Online (fake for dev; UPI shows fake UPI ID).
"""
import re
from typing import Optional, Tuple

from app.db.supabase_client import get_supabase
from app.services.booking_service import (
    create_booking,
    estimate_price,
    is_pune_address,
    get_nearby_outlets_message,
    get_nearby_outlet_for_address,
    FAKE_UPI_ID,
)
from app.services.tracking_service import get_order_by_number, get_orders_for_customer
from app.services.rag_service import answer_with_rag
from app.services.nl_query_service import answer_order_query
from app.services.conversation_memory import (
    append as memory_append,
    get_formatted_history as get_memory_history,
    get_user_questions as get_memory_user_questions,
    clear as memory_clear,
)

# state: name, address, phone, delivery_type, service_choice, step, weight_kg, weight_note, customer_instructions
_booking_state: dict = {}


def _progress(_step: str) -> str:
    """Return empty string. Do not add step progress (e.g. 'Step 1 of 12') to any message."""
    return ""


def _get_welcome_message() -> str:
    """Creative welcome with services and quick actions (icons, engaging copy)."""
    return (
        "✨ <b>Welcome to LaundryOps!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👕 <i>Fresh clothes, zero hassle — we’re here for you.</i>\n\n"
        "🧺 <b>What we do</b>\n"
        "• Wash · Wash+Iron · Dry clean · Shoe · Home textiles (bedsheet, carpet, curtains) · Premium/Press/Steam iron\n"
        "• 🚚 Pickup & delivery or you drop at our outlet\n"
        "• ⚡ Standard (48 hrs) or Express (24 hrs)\n\n"
        "🚀 <b>What would you like to do?</b>\n\n"
        "📦 <b>Book</b> — Schedule a pickup, we’ll handle the rest\n"
        "🔍 <b>Track</b> — Check status (Order ID e.g. ORD-1234ABCD)\n"
        "💰 <b>Pricing</b> — Services & fees\n"
        "🛟 <b>Support</b> — Policies, FAQ & help\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 Just type <b>Book</b>, <b>Track</b>, or ask: <i>\"Where is my order?\"</i>"
    )


def _is_greeting_or_casual(message: str) -> bool:
    """True if message looks like a greeting or casual chat (hi, hello, how are you, what are you doing, etc.)."""
    m = message.strip().lower()
    if not m or len(m) > 120:
        return False
    greetings = (
        "hi", "hello", "hey", "hii", "heyy", "helo", "hallo", "hi there", "hey there",
        "good morning", "good evening", "good afternoon", "gm", "ge", "ga",
        "namaste", "namaskar", "sup", "yo", "hola",
    )
    if m in greetings or m.rstrip("!?.") in greetings:
        return True
    casual = (
        "how are you", "how r u", "how ru", "what are you doing", "what do you do",
        "what can you do", "tell me about you", "who are you", "who r u",
        "kya kar rahe ho", "kaise ho", "aap kya karte ho", "help", "intro",
        "what is this", "what's this", "ye kya hai", "start", "begin",
    )
    return any(c in m for c in casual)


def _reply_to_greeting_or_casual(message: str) -> str:
    """Short friendly reply line (optional) + welcome. Makes the bot feel conversational."""
    m = message.strip().lower()
    if any(x in m for x in ("hi", "hello", "hey", "hii", "heyy", "namaste", "gm", "ge", "ga")):
        return "Hey! 👋 Great to hear from you.\n\n" + _get_welcome_message()
    if any(x in m for x in ("how are you", "how r u", "kaise ho", "how ru")):
        return "I’m doing great, thanks for asking! 😊 Ready to help with your laundry.\n\n" + _get_welcome_message()
    if any(x in m for x in ("what are you doing", "what do you do", "kya kar rahe ho", "what can you do", "tell me about", "who are you")):
        return "I’m your laundry buddy! 🧺 Here to help you book pickups, track orders, and get fresh clothes back.\n\n" + _get_welcome_message()
    if any(x in m for x in ("help", "intro", "what is this", "ye kya hai", "start", "begin")):
        return "Sure, here’s what I can do for you —\n\n" + _get_welcome_message()
    return _get_welcome_message()


def _is_show_my_questions_intent(message: str) -> bool:
    """True if user wants to see what they asked (recent questions from memory)."""
    m = message.strip().lower()
    if not m or len(m) > 80:
        return False
    phrases = (
        "what did i ask", "what did i say", "my questions", "show my questions",
        "my messages", "show my messages", "conversation history", "my history",
        "what questions did i ask", "list my questions", "maine kya pucha",
        "mera kya question tha", "jo maine pucha", "my recent questions",
    )
    return any(p in m for p in phrases)


def _reply_with_recent_questions(chat_id: str) -> str:
    """Format recent user questions from conversation memory for display."""
    questions = get_memory_user_questions(chat_id)
    if not questions:
        return (
            "📋 <b>Your recent questions</b>\n\n"
            "No questions in this chat yet — or you just said <b>/start</b> and we cleared the history.\n\n"
            "Ask me anything (e.g. pricing, track, book) and then ask <i>\"What did I ask?\"</i> to see your questions here."
        )
    lines = []
    for i, q in enumerate(questions, 1):
        q_short = (q[:80] + "…") if len(q) > 80 else q
        lines.append(f"{i}. {q_short}")
    return (
        "📋 <b>Questions you asked in this chat</b>\n\n"
        + "\n".join(lines)
        + "\n\n<i>This is from our recent conversation. Say /start to clear and start fresh.</i>"
    )


# Rough weight per item (kg) when customer gives pieces instead of kg
_WEIGHT_PER_SHIRT = 0.2
_WEIGHT_PER_PANT = 0.25
_WEIGHT_PER_PIECE = 0.2
_WEIGHT_PER_SHOE_PAIR = 0.5
_WEIGHT_PER_IRON_PIECE = 0.2


def _parse_weight_from_message(raw: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse weight: either kg (number) or pieces (e.g. "5 shirts 2 pants", "8 pieces", "10 clothes").
    Returns (weight_kg, weight_note). weight_note is set when estimated from pieces (e.g. "5 shirts, 2 pants").
    """
    raw_clean = (raw or "").strip().lower().replace(",", " ")
    # Try plain number first (kg)
    try:
        w = float(raw.replace(",", ".").strip())
        if 0.5 <= w <= 100:
            return (round(w, 2), None)
    except ValueError:
        pass
    # Parse "X shirt(s)", "X pant(s)", "X piece(s)", "X clothes"
    shirts = 0
    pants = 0
    pieces_generic = 0
    # e.g. "5 shirts 2 pants", "3 shirt 4 pant", "8 pieces", "10 clothes"
    m_shirts = re.search(r"(\d+)\s*shirts?", raw_clean)
    if m_shirts:
        shirts = int(m_shirts.group(1))
    m_pants = re.search(r"(\d+)\s*pants?", raw_clean)
    if m_pants:
        pants = int(m_pants.group(1))
    m_pieces = re.search(r"(\d+)\s*pieces?", raw_clean)
    if m_pieces:
        pieces_generic = int(m_pieces.group(1))
    m_clothes = re.search(r"(\d+)\s*clothes?", raw_clean)
    if m_clothes:
        pieces_generic = int(m_clothes.group(1))
    # Single number with "shirt/pant/piece/clothes" might be "5 shirt" (no s)
    if shirts == 0 and pants == 0 and pieces_generic == 0:
        m = re.search(r"(\d+)\s*(shirt|pant|piece|clothes?)", raw_clean)
        if m:
            n, word = int(m.group(1)), (m.group(2) or "").rstrip("s")
            if "shirt" in word:
                shirts = n
            elif "pant" in word:
                pants = n
            else:
                pieces_generic = n
    total_kg = shirts * _WEIGHT_PER_SHIRT + pants * _WEIGHT_PER_PANT + pieces_generic * _WEIGHT_PER_PIECE
    if total_kg < 0.5:
        return (None, None)
    total_kg = round(min(100.0, total_kg), 2)
    parts = []
    if shirts:
        parts.append(f"{shirts} shirt{'s' if shirts != 1 else ''}")
    if pants:
        parts.append(f"{pants} pant{'s' if pants != 1 else ''}")
    if pieces_generic:
        parts.append(f"{pieces_generic} piece{'s' if pieces_generic != 1 else ''}")
    weight_note = ", ".join(parts) if parts else None
    return (total_kg, weight_note)


def _parse_quantity(raw: str, min_val: int = 1, max_val: int = 100) -> Optional[int]:
    """Parse a positive integer from message (e.g. '3', '5 pairs', '10'). Returns None if invalid or out of range."""
    if not (raw or "").strip():
        return None
    s = (raw or "").strip()
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    try:
        n = int(m.group(1))
        if min_val <= n <= max_val:
            return n
    except ValueError:
        pass
    return None


def _parse_home_textiles_weight(raw: str, textile_type: str) -> Tuple[Optional[float], Optional[str]]:
    """Parse home textiles: '2 bedsheets', '1 carpet', '3 curtains' or plain weight '3' (kg). Returns (weight_kg, note)."""
    s = (raw or "").strip().lower()
    # Plain number = weight in kg
    m = re.search(r"^(\d+(?:\.\d+)?)\s*kg?$", s)
    if m:
        try:
            w = float(m.group(1))
            if 0.5 <= w <= 100:
                return (round(w, 2), f"{w} kg")
        except ValueError:
            pass
    # "2" alone = 2 kg or 2 items depending on type
    m = re.search(r"^(\d+)$", s)
    if m:
        try:
            n = int(m.group(1))
            if n < 1 or n > 100:
                return (None, None)
            # Approximate: 1 bedsheet ~1 kg, 1 carpet ~3 kg, 1 curtain ~0.5 kg
            if textile_type == "bedsheet":
                return (round(n * 1.0, 2), f"{n} bedsheet{'s' if n != 1 else ''}")
            if textile_type == "carpet":
                return (round(n * 3.0, 2), f"{n} carpet{'s' if n != 1 else ''}")
            if textile_type == "curtains":
                return (round(n * 0.5, 2), f"{n} curtain{'s' if n != 1 else ''}")
            return (round(n * 1.0, 2), f"{n} item{'s' if n != 1 else ''}")
        except ValueError:
            pass
    # "2 bedsheets", "1 carpet", "3 curtains"
    for pattern, label, kg_each in [
        (r"(\d+)\s*bedsheets?", "bedsheet", 1.0),
        (r"(\d+)\s*carpets?", "carpet", 3.0),
        (r"(\d+)\s*curtains?", "curtain", 0.5),
    ]:
        m = re.search(pattern, s)
        if m:
            try:
                n = int(m.group(1))
                if 1 <= n <= 100:
                    w = round(n * kg_each, 2)
                    note = f"{n} {label}{'s' if n != 1 else ''}"
                    return (max(0.5, w), note)
            except ValueError:
                pass
    return (None, None)


def handle_message(chat_id: str, text: str) -> str:
    raw = (text or "").strip()
    reply = _handle_message_impl(chat_id, text, raw)
    memory_append(chat_id, raw, reply)
    return reply


def _handle_message_impl(chat_id: str, text: str, raw: str) -> str:
    message = (raw or "").strip().lower()

    # 0) Optional rating after booking (reply 1-5 or skip)
    state = _booking_state.get(chat_id)
    if state and state.get("step") == "awaiting_rating":
        order_id = state.get("order_id")
        _booking_state.pop(chat_id, None)
        if raw.lower() in ("skip", "no", "n", "later", "-"):
            return "👍 No problem — you can rate later from the app or when we ask again."
        try:
            rating = int(raw.strip())
            if 1 <= rating <= 5 and order_id:
                supabase = get_supabase()
                supabase.table("feedback").insert({"order_id": order_id, "rating": rating}).execute()
                return "⭐ Thanks for your rating! We really appreciate it. 🙏"
        except ValueError:
            pass
        except Exception:
            pass  # feedback table may not exist; still clear state
        return "👍 You can rate later (reply 1–5 or skip next time)."

    # 1) Booking flow state machine
    state = _booking_state.get(chat_id)
    if state:
        step = state.get("step")
        if step == "name":
            state["name"] = raw
            state["step"] = "address"
            _booking_state[chat_id] = state
            nearby = get_nearby_outlets_message()
            return (
                _progress("address")
                + f"👋 Nice to meet you, <b>{raw}</b>!\n\n"
                "📍 Send your <b>address</b> in one message.\n"
                "<i>We currently serve Pune only.</i>\n\n"
                + nearby
            )
        if step == "address":
            # If user typed "skip", don't move forward — ask for address/area and show outlets
            if raw.lower().strip() == "skip":
                _booking_state[chat_id] = state
                nearby = get_nearby_outlets_message()
                return (
                    _progress("address")
                    + "📍 We need your <b>address</b> or <b>area</b> to find your nearest store.\n"
                    "Try: <i>Viman Nagar, Baner, Kothrud</i> or your full address.\n\n"
                    + nearby
                )
            # Pune-only: accept if "pune" or any Pune area (e.g. Viman Nagar, Kothrud)
            if not is_pune_address(raw):
                _booking_state[chat_id] = state
                nearby = get_nearby_outlets_message()
                return (
                    _progress("address")
                    + "🌍 We’re in <b>Pune</b> right now!\n"
                    "Send your area or full address — e.g. <i>Viman Nagar, Kothrud, Hinjewadi, Baner</i>.\n\n"
                    + nearby
                )
            state["address"] = raw.strip()
            state["step"] = "phone"
            _booking_state[chat_id] = state
            nearby_info = get_nearby_outlet_for_address(raw.strip())
            if nearby_info:
                area_name, outlet_name, is_active = nearby_info
                prefix = f"🏪 Your nearest store: <b>{outlet_name}</b> ({area_name}).\n\n"
                if not is_active:
                    prefix += "<i>That outlet is on maintenance; we’ll assign another when you book.</i>\n\n"
            else:
                prefix = ""
            return _progress("phone") + prefix + "📞 Send your <b>phone number</b> so we can confirm your booking."
        if step == "phone":
            state["phone"] = raw
            state["step"] = "delivery"
            _booking_state[chat_id] = state
            return (
                _progress("delivery")
                + "🚚 <b>When do you need it?</b>\n\n"
                "• <b>1</b> — Standard (about 48 hrs)\n"
                "• <b>2</b> — Express (about 24 hrs, +30% fee)\n\n"
                "Reply with <b>1</b> or <b>2</b>."
            )
        if step == "delivery":
            state["delivery_type"] = "express" if message in ("2", "express") else "standard"
            state["step"] = "service"
            _booking_state[chat_id] = state
            return (
                _progress("service")
                + "🧺 <b>Pick a service</b>\n\n"
                "• <b>1</b> — Wash only\n"
                "• <b>2</b> — Wash + Iron\n"
                "• <b>3</b> — Dry clean\n"
                "• <b>4</b> — Shoe clean\n"
                "• <b>5</b> — Home textiles (bedsheet, carpet, curtains)\n"
                "• <b>6</b> — Premium ironing\n"
                "• <b>7</b> — Press iron\n"
                "• <b>8</b> — Steam iron\n\n"
                "Reply with <b>1</b>–<b>8</b>."
            )
        if step == "service":
            choice_map = {
                "1": "wash_only", "2": "wash_iron", "3": "dry_clean", "4": "shoe_clean",
                "5": "home_textiles", "6": "premium_iron", "7": "press_iron", "8": "steam_iron",
            }
            state["service_choice"] = choice_map.get(message, "wash_only")
            _booking_state[chat_id] = state
            # Dynamic next step based on service
            if state["service_choice"] == "shoe_clean":
                state["step"] = "shoe_quantity"
                return (
                    _progress("shoe_quantity")
                    + "👟 <b>Shoe clean</b> — How many <b>pairs of shoes</b>?\n\n"
                    "Reply with a number (e.g. 1, 2, 5). We charge per pair."
                )
            if state["service_choice"] == "home_textiles":
                state["step"] = "home_textiles_type"
                return (
                    _progress("home_textiles_type")
                    + "🛏️ <b>Home textiles</b> — What type?\n\n"
                    "• <b>1</b> — Bedsheet / bedsheets\n"
                    "• <b>2</b> — Carpet / rug\n"
                    "• <b>3</b> — Curtains\n\n"
                    "Reply with <b>1</b>, <b>2</b>, or <b>3</b>."
                )
            if state["service_choice"] in ("premium_iron", "press_iron", "steam_iron"):
                state["step"] = "iron_quantity"
                return (
                    _progress("iron_quantity")
                    + "👔 <b>Ironing</b> — How many <b>pieces</b> to iron?\n\n"
                    "Reply with a number (e.g. 5, 10) or <b>weight in kg</b> (e.g. 2 kg)."
                )
            # wash_only, wash_iron, dry_clean → ask weight
            state["step"] = "weight"
            return (
                _progress("weight")
                + "⚖️ <b>How much laundry?</b>\n\n"
                "Send <b>weight in kg</b> (e.g. 2 or 3.5) or <b>clothes count</b>:\n"
                "• <b>5 shirts, 2 pants</b>\n"
                "• <b>8 pieces</b> or <b>10 clothes</b>\n\n"
                "<i>We’ll estimate weight and show your bill.</i>"
            )
        if step == "shoe_quantity":
            qty = _parse_quantity(raw, min_val=1, max_val=20)
            if qty is None:
                _booking_state[chat_id] = state
                return (
                    _progress("shoe_quantity")
                    + "👟 How many <b>pairs of shoes</b>? Reply with a number (1–20)."
                )
            state["weight_kg"] = round(qty * _WEIGHT_PER_SHOE_PAIR, 2)
            state["weight_note"] = f"{qty} pair{'s' if qty != 1 else ''} of shoes"
            state["step"] = "pickup_type"
            _booking_state[chat_id] = state
            total_bill = estimate_price(
                state.get("service_choice", "shoe_clean"),
                state["weight_kg"],
                state.get("delivery_type", "standard"),
            )
            bill_msg = f"💵 <b>{qty} pair{'s' if qty != 1 else ''} of shoes</b> — Total: <b>₹{total_bill or 0}</b>.\n\n" if total_bill else ""
            return (
                _progress("pickup_type")
                + bill_msg
                + "📍 <b>Pickup option</b>\n\n"
                "• <b>1</b> — I’ll drop at outlet (you bring shoes to store)\n"
                "• <b>2</b> — Pickup from my address (we pick up & deliver back)\n\n"
                "Reply with <b>1</b> or <b>2</b>."
            )
        if step == "home_textiles_type":
            type_map = {"1": "bedsheet", "2": "carpet", "3": "curtains"}
            state["home_textiles_type"] = type_map.get(message, "bedsheet")
            state["step"] = "weight"
            _booking_state[chat_id] = state
            type_label = state["home_textiles_type"].title()
            return (
                _progress("weight")
                + f"🛏️ <b>Home textiles ({type_label})</b> — How many items or weight?\n\n"
                "Send <b>number of items</b> (e.g. 2 bedsheets, 1 carpet) or <b>weight in kg</b> (e.g. 3 kg)."
            )
        if step == "iron_quantity":
            # Accept number of pieces (e.g. 5, 10) or weight (e.g. 2 or 2.5)
            qty = _parse_quantity(raw, min_val=1, max_val=100)
            if qty is not None:
                state["weight_kg"] = round(max(0.5, qty * _WEIGHT_PER_IRON_PIECE), 2)
                state["weight_note"] = f"{int(qty)} piece{'s' if qty != 1 else ''} to iron"
            else:
                weight_kg, weight_note = _parse_weight_from_message(raw)
                if weight_kg is None or weight_kg < 0.5 or weight_kg > 100:
                    _booking_state[chat_id] = state
                    return (
                        _progress("iron_quantity")
                        + "👔 Reply with <b>number of pieces</b> (e.g. 5, 10) or <b>weight in kg</b> (e.g. 2)."
                    )
                state["weight_kg"] = weight_kg
                state["weight_note"] = weight_note or f"{weight_kg} kg"
            state["step"] = "pickup_type"
            _booking_state[chat_id] = state
            total_bill = estimate_price(
                state.get("service_choice", "premium_iron"),
                state["weight_kg"],
                state.get("delivery_type", "standard"),
            )
            bill_msg = f"💵 Your total: <b>₹{total_bill or 0}</b>.\n\n" if total_bill else ""
            return (
                _progress("pickup_type")
                + bill_msg
                + "📍 <b>Pickup option</b>\n\n"
                "• <b>1</b> — I’ll drop at outlet\n"
                "• <b>2</b> — Pickup from my address\n\n"
                "Reply with <b>1</b> or <b>2</b>."
            )
        if step == "weight":
            if state.get("service_choice") == "home_textiles" and state.get("home_textiles_type"):
                weight_kg, weight_note = _parse_home_textiles_weight(raw, state["home_textiles_type"])
            else:
                weight_kg, weight_note = _parse_weight_from_message(raw)
            if weight_kg is None:
                _booking_state[chat_id] = state
                if state.get("service_choice") == "home_textiles":
                    return (
                        _progress("weight")
                        + "🛏️ Send <b>number of items</b> (e.g. 2, 3) or <b>weight in kg</b> (e.g. 2 kg)."
                    )
                return (
                    _progress("weight")
                    + "⚖️ Send weight in <b>kg</b> (e.g. 2 or 3.5) or <b>clothes count</b> "
                    "(e.g. 5 shirts, 2 pants or 8 pieces)."
                )
            if weight_kg < 0.5 or weight_kg > 100:
                _booking_state[chat_id] = state
                return _progress("weight") + "⚖️ Weight must be between <b>0.5</b> and <b>100 kg</b> (or equivalent pieces)."
            state["weight_kg"] = weight_kg
            state["weight_note"] = weight_note
            state["step"] = "pickup_type"
            _booking_state[chat_id] = state
            # Show estimated total bill for this weight
            total_bill = estimate_price(
                state.get("service_choice", "wash_only"),
                weight_kg,
                state.get("delivery_type", "standard"),
            )
            if total_bill is not None:
                if weight_note:
                    bill_msg = f"💵 Estimated <b>{weight_kg} kg</b> (from {weight_note}). Your total: <b>₹{total_bill}</b>.\n\n"
                else:
                    bill_msg = f"💵 Your total for <b>{weight_kg} kg</b>: <b>₹{total_bill}</b>.\n\n"
            else:
                bill_msg = ""
            return (
                _progress("pickup_type")
                + bill_msg
                + "📍 <b>Pickup option</b>\n\n"
                "• <b>1</b> — I’ll drop at outlet (you bring clothes to store)\n"
                "• <b>2</b> — Pickup from my address (we pick up & deliver back)\n\n"
                "Reply with <b>1</b> or <b>2</b>."
            )
        if step == "pickup_type":
            pickup_type = "home_pickup" if message in ("2", "home", "pickup") else "self_drop"
            state["pickup_type"] = pickup_type
            if pickup_type == "home_pickup":
                state["step"] = "home_address"
                _booking_state[chat_id] = state
                return (
                    _progress("home_address")
                    + "🏠 <b>Pickup & delivery address</b>\n\n"
                    "Send your <b>full address</b>. We’ll pick up from here and deliver back when ready."
                )
            state["step"] = "pickup_datetime"
            _booking_state[chat_id] = state
            return (
                _progress("pickup_datetime")
                + "📅 <b>Preferred date & time to drop off at outlet?</b>\n\n"
                "e.g. Tomorrow 10am, or 15 Feb 2–4pm — type your preferred slot."
            )
        if step == "home_address":
            home_addr = raw.strip() if raw.strip() else ""
            if not home_addr:
                _booking_state[chat_id] = state
                return _progress("home_address") + "🏠 Please send your full address for pickup and delivery."
            state["pickup_address"] = home_addr
            state["delivery_address"] = home_addr
            state["step"] = "pickup_datetime"
            _booking_state[chat_id] = state
            return (
                _progress("pickup_datetime")
                + "📅 <b>Preferred pickup date & time?</b>\n\n"
                "When should we pick up from your address? e.g. Tomorrow 10am, or 15 Feb 2–4pm."
            )
        if step == "pickup_datetime":
            state["preferred_pickup_at"] = (raw or "").strip() or ""
            state["step"] = "delivery_datetime"
            _booking_state[chat_id] = state
            pickup_type = state.get("pickup_type", "self_drop")
            if pickup_type == "home_pickup":
                return (
                    _progress("delivery_datetime")
                    + "📅 <b>Preferred delivery date & time?</b>\n\n"
                    "When should we deliver back? e.g. Day after 6pm, or 16 Feb 10am–12pm."
                )
            return (
                _progress("delivery_datetime")
                + "📅 <b>Preferred date & time to pick up from outlet?</b>\n\n"
                "When will you collect? e.g. 17 Feb 11am, or Saturday 2–4pm."
            )
        if step == "delivery_datetime":
            state["preferred_delivery_at"] = (raw or "").strip() or ""
            state["step"] = "instructions"
            _booking_state[chat_id] = state
            return (
                _progress("instructions")
                + "📝 <b>Any special instructions?</b>\n\n"
                "e.g. delicate, no softener, folding preference — or type <b>no</b> / <b>none</b> to skip."
            )
        if step == "instructions":
            instructions = raw.strip() if raw.strip() else ""
            if instructions and instructions.lower() in ("no", "none", "nope", "skip", "-"):
                instructions = ""
            state["customer_instructions"] = instructions
            state["step"] = "payment"
            _booking_state[chat_id] = state
            return (
                _progress("payment")
                + "💰 <b>How would you like to pay?</b>\n\n"
                "• <b>1</b> — 💵 Cash on delivery (pay when we deliver)\n"
                "• <b>2</b> — 📱 UPI (pay to our UPI ID now or later)\n"
                "• <b>3</b> — 💳 Card / Online payment\n\n"
                "Reply with <b>1</b>, <b>2</b>, or <b>3</b>."
            )
        if step == "payment":
            # Map 1/2/3 or cash/upi/card to cod/upi/online
            pm = message.strip()
            if pm in ("1", "cash", "cod", "cash on delivery"):
                payment_method = "cod"
            elif pm in ("2", "upi"):
                payment_method = "upi"
            elif pm in ("3", "card", "online", "netbanking"):
                payment_method = "online"
            else:
                _booking_state[chat_id] = state
                return (
                    _progress("payment")
                    + "💰 Choose how you’d like to pay:\n\n"
                    "• <b>1</b> — Cash on delivery\n"
                    "• <b>2</b> — UPI\n"
                    "• <b>3</b> — Card / Online\n\n"
                    "Reply with <b>1</b>, <b>2</b>, or <b>3</b>."
                )
            state["payment_method"] = payment_method
            _booking_state.pop(chat_id, None)
            address = state.get("address", "")
            pickup_type = state.get("pickup_type", "self_drop")
            pickup_address = state.get("pickup_address", "") if pickup_type == "home_pickup" else ""
            delivery_address = state.get("delivery_address", "") if pickup_type == "home_pickup" else ""
            preferred_pickup_at = (state.get("preferred_pickup_at") or "").strip() or None
            preferred_delivery_at = (state.get("preferred_delivery_at") or "").strip() or None
            try:
                result = create_booking(
                    chat_id,
                    full_name=state.get("name", ""),
                    address=address,
                    phone=state.get("phone", ""),
                    delivery_type=state.get("delivery_type", "standard"),
                    service_choice=state.get("service_choice", "wash_only"),
                    weight_kg=state.get("weight_kg", 1.0),
                    weight_note=state.get("weight_note"),
                    customer_instructions=state.get("customer_instructions", ""),
                    pickup_type=pickup_type,
                    pickup_address=pickup_address,
                    delivery_address=delivery_address,
                    payment_method=payment_method,
                    preferred_pickup_at=preferred_pickup_at,
                    preferred_delivery_at=preferred_delivery_at,
                )
                if result.get("error") == "setup":
                    return result.get("message", "Please run the Supabase migration (see docs).")
                if result.get("error") == "no_outlets":
                    return "⚠️ " + (result.get("message") or "All outlets are currently on maintenance. Please try again later.")
                welcome = (
                    "🎉 <b>Booking confirmed!</b> 🎉\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                )
                services_str = ", ".join((s.replace("_", " ").title() for s in result.get("services", [])))
                weight_line = f"{result.get('weight_kg', 1)} kg"
                if result.get("weight_note"):
                    weight_line += f" (from {result['weight_note']})"
                delivery_type_str = "Express (≈24 hrs)" if result.get("is_express") else "Standard (≈48 hrs)"
                pm = (result.get("payment_method") or "cod").strip().lower()
                if pm == "upi":
                    payment_line = f"💰 <b>Payment:</b> UPI — Pay to <code>{FAKE_UPI_ID}</code>\n"
                elif pm == "online":
                    payment_line = "💰 <b>Payment:</b> Card/Online — Link will be shared separately.\n"
                else:
                    payment_line = "💰 <b>Payment:</b> Cash on delivery (pay when we deliver).\n"
                msg = (
                    welcome
                    + "📋 <b>Booking details</b>\n"
                    + "━━━━━━━━━━━━━━━━━━━━\n"
                    + f"📌 <b>Order ID:</b> <code>{result['order_number']}</code>\n"
                    + f"🧺 <b>Services:</b> {services_str}\n"
                    + f"⚖️ <b>Weight:</b> {weight_line}\n"
                    + f"🚚 <b>Delivery:</b> {delivery_type_str}\n"
                    + f"🏪 <b>Outlet:</b> {result['outlet_name']}\n"
                    + f"⏱ <b>Expected:</b> in about {result['expected_hours']} hours\n"
                    + f"💵 <b>Total:</b> ₹{result.get('total_price', 0)}\n"
                    + payment_line
                )
                if result.get("customer_instructions"):
                    msg += f"📝 <b>Your instructions:</b> {result['customer_instructions']}\n"
                if result.get("pickup_type") == "home_pickup":
                    msg += f"🏠 <b>Pickup & delivery:</b>\n{result.get('pickup_address') or address}\n"
                    if result.get("preferred_pickup_at"):
                        msg += f"📅 <b>Preferred pickup:</b> {result['preferred_pickup_at']}\n"
                    if result.get("preferred_delivery_at"):
                        msg += f"📅 <b>Preferred delivery:</b> {result['preferred_delivery_at']}\n"
                    msg += "\n<i>We’ll pick up from here and deliver back when ready.</i>"
                    if result.get("is_express"):
                        msg += " Express: early pickup and drop."
                else:
                    msg += "\n📍 <b>Drop-off:</b> You can drop your clothes at the outlet."
                    if result.get("preferred_pickup_at"):
                        msg += f"\n📅 <b>Preferred drop-off:</b> {result['preferred_pickup_at']}"
                    if result.get("preferred_delivery_at"):
                        msg += f"\n📅 <b>Preferred pick-up from outlet:</b> {result['preferred_delivery_at']}"
                if result.get("maintenance_note"):
                    msg += "\n\n⚠️ " + result["maintenance_note"]
                msg += "\n\n━━━━━━━━━━━━━━━━━━━━\n"
                msg += "📦 Use <b>Track</b> or ask <i>\"Where is my order?\"</i> for updates.\n\n"
                msg += "⭐ <b>Rate your experience?</b> (optional) Reply <b>1–5</b> or <b>skip</b>."
                _booking_state[chat_id] = {"step": "awaiting_rating", "order_id": result.get("order_id")}
                return msg
            except Exception as e:
                err = str(e)
                if "telegram_chat_id" in err and "does not exist" in err:
                    return (
                        "⚠️ Setup needed: In Supabase SQL Editor run:\n"
                        "<code>ALTER TABLE customers ADD COLUMN telegram_chat_id TEXT UNIQUE;</code>"
                    )
                return f"Sorry, we couldn't create the booking. Please try again or contact the outlet. ({err[:60]})"

    # 2) /start → full welcome (services + quick actions); clear conversation memory for fresh context
    if message == "/start" or message == "start":
        memory_clear(chat_id)
        return _get_welcome_message()

    # 3) Greetings & casual chat (hi, hello, how are you, what can you do, etc.) → friendly reply + welcome
    if _is_greeting_or_casual(message):
        return _reply_to_greeting_or_casual(message)

    # 3b) "What did I ask?" / "My questions" → show recent questions from conversation memory
    if _is_show_my_questions_intent(message):
        return _reply_with_recent_questions(chat_id)

    # 4) Order-related NL (before Book so "my order"/"my booking" don't start new book)
    if _is_order_related(message):
        return answer_order_query(chat_id, text, conversation_history=get_memory_history(chat_id))

    # 5) Book intent → start flow (ask name first)
    if any(w in message for w in ("book", "pickup", "schedule", "order lagana", "laundry bhejo")):
        _booking_state[chat_id] = {"step": "name"}
        return (
            _progress("name")
            + "👋 <b>Let’s get your laundry sorted!</b>\n\n"
            "📌 Send your <b>full name</b> to get started."
        )

    # 6) Track by order number
    order_num = _extract_order_number(message, text)
    if order_num:
        order = get_order_by_number(order_num)
        if order:
            items_str = order.get("items_summary") or "—"
            delivery = order.get("delivery_time") or "—"
            return (
                "📦 <b>Order status</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <code>{order.get('order_number')}</code>\n"
                f"📊 Status: <b>{order.get('status', 'Unknown')}</b>\n"
                f"🧺 Services: {items_str}\n"
                f"⏱ Expected: {delivery}\n"
                f"🏪 Outlet: {order.get('outlet_name', '—')}"
            )
        return f"🔍 Order <code>{order_num}</code> not found. Double-check the ID or type <b>Book</b> to place a new order."

    # 7) Track without order number
    if any(w in message for w in ("track", "status", "where is my order", "kahan hai")):
        orders = get_orders_for_customer(chat_id, limit=1)
        if not orders:
            return "📦 Send your <b>Order ID</b> (e.g. ORD-1234ABCD) to track, or type <b>Book</b> to schedule a pickup."
        o = get_order_by_number(orders[0]["order_number"])
        if o:
            items_str = o.get("items_summary") or "—"
            delivery = o.get("delivery_time") or "—"
            return (
                "📦 <b>Your latest order</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <code>{o.get('order_number')}</code>\n"
                f"📊 Status: <b>{o.get('status', 'Unknown')}</b>\n"
                f"🧺 Services: {items_str}\n"
                f"⏱ Expected: {delivery}\n"
                f"🏪 Outlet: {o.get('outlet_name', '—')}"
            )
        return "📦 Send your <b>Order ID</b> (e.g. ORD-1234ABCD) to track."

    # 8) Pricing / support → RAG (with conversation memory for follow-ups)
    if any(w in message for w in ("price", "pricing", "cost", "fee", "support", "complaint", "policy", "faq", "rewash", "delivery time", "express")):
        return answer_with_rag(text, conversation_history=get_memory_history(chat_id))

    # 9) Default: try RAG for general questions, else engaging menu
    rag_reply = answer_with_rag(text, conversation_history=get_memory_history(chat_id))
    if rag_reply and "don't have" not in rag_reply.lower() and "no specific" not in rag_reply.lower():
        return rag_reply
    return (
        "💬 I’m not sure I got that — but I’m here to help!\n\n"
        "📦 <b>Book</b> — Schedule a pickup\n"
        "🔍 <b>Track</b> — Send your Order ID\n"
        "💰 <b>Pricing</b> / 🛟 <b>Support</b> — Just ask!\n\n"
        "<i>Try: \"Hi\", \"Book\", \"Where is my order?\" or \"Kitna time lagega?\"</i>"
    )


def _extract_order_number(lower_message: str, original_text: str) -> Optional[str]:
    import re
    m = re.search(r"ord-?([a-f0-9]{8})\b", lower_message)
    if m:
        return "ORD-" + m.group(1).upper()
    m = re.search(r"ORD-?([A-Za-z0-9]{4,})", original_text.strip())
    if m:
        return "ORD-" + m.group(1).upper()
    return None


def _is_order_related(message: str) -> bool:
    keywords = (
        "order", "my order", "my booking", "mera order", "kitna time", "kab milega",
        "details", "status", "kahan hai", "delivery", "time lagega", "lagenge",
        "track", "check", "batao", "bata", "tell me", "update", "about my"
    )
    return any(k in message for k in keywords)
