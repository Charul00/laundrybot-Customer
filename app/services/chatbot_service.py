"""
Intent router + booking flow. Booking steps: name → address → phone → delivery → service → weight → pickup → instructions → create.
Handles: /start, book, track, pricing, support, and natural-language order queries.
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
)
from app.services.tracking_service import get_order_by_number, get_orders_for_customer
from app.services.rag_service import answer_with_rag
from app.services.nl_query_service import answer_order_query

# state: name, address, phone, delivery_type, service_choice, step, weight_kg, weight_note, customer_instructions
_booking_state: dict = {}

# Rough weight per item (kg) when customer gives pieces instead of kg
_WEIGHT_PER_SHIRT = 0.2
_WEIGHT_PER_PANT = 0.25
_WEIGHT_PER_PIECE = 0.2


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


def handle_message(chat_id: str, text: str) -> str:
    message = (text or "").strip().lower()
    raw = (text or "").strip()

    # 0) Optional rating after booking (reply 1-5 or skip)
    state = _booking_state.get(chat_id)
    if state and state.get("step") == "awaiting_rating":
        order_id = state.get("order_id")
        _booking_state.pop(chat_id, None)
        if raw.lower() in ("skip", "no", "n", "later", "-"):
            return "No problem. You can rate later from the app or when we ask again."
        try:
            rating = int(raw.strip())
            if 1 <= rating <= 5 and order_id:
                supabase = get_supabase()
                supabase.table("feedback").insert({"order_id": order_id, "rating": rating}).execute()
                return "Thanks for your rating! 🙏"
        except ValueError:
            pass
        except Exception:
            pass  # feedback table may not exist; still clear state
        return "No problem. You can rate later (reply 1-5 or skip next time)."

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
                "Got it. Please send your <b>address</b> (one message). We currently serve <b>Pune</b> only.\n\n"
                + nearby
            )
        if step == "address":
            # If user typed "skip", don't move forward — ask for address/area and show outlets
            if raw.lower().strip() == "skip":
                _booking_state[chat_id] = state
                nearby = get_nearby_outlets_message()
                return (
                    "Please send your <b>address</b> or <b>area</b> to continue. "
                    "You can send your area (e.g. Viman Nagar, Baner, Kothrud) or your full address.\n\n"
                    + nearby
                )
            # Pune-only: accept if "pune" or any Pune area (e.g. Viman Nagar, Kothrud)
            if not is_pune_address(raw):
                _booking_state[chat_id] = state
                nearby = get_nearby_outlets_message()
                return (
                    "We currently serve <b>Pune</b> only. "
                    "Viman Nagar, Kothrud, Hinjewadi, Baner, etc. are in Pune. "
                    "Please send your address or area.\n\n"
                    + nearby
                )
            state["address"] = raw.strip()
            state["step"] = "phone"
            _booking_state[chat_id] = state
            nearby_info = get_nearby_outlet_for_address(raw.strip())
            if nearby_info:
                area_name, outlet_name, is_active = nearby_info
                prefix = f"Your nearby store is <b>{outlet_name}</b> ({area_name}). "
                if not is_active:
                    prefix += "(That outlet is on maintenance; we'll assign another when you book.) "
            else:
                prefix = ""
            return prefix + "Thanks. Please send your <b>phone number</b> to confirm."
        if step == "phone":
            state["phone"] = raw
            state["step"] = "delivery"
            _booking_state[chat_id] = state
            return (
                "Choose <b>delivery</b>:\n"
                "• Reply <b>1</b> for <b>Standard</b> (about 48 hours)\n"
                "• Reply <b>2</b> for <b>Express</b> (about 24 hours, +30% fee)"
            )
        if step == "delivery":
            state["delivery_type"] = "express" if message in ("2", "express") else "standard"
            state["step"] = "service"
            _booking_state[chat_id] = state
            return (
                "Choose <b>service</b>:\n"
                "• <b>1</b> – Wash only\n"
                "• <b>2</b> – Wash + Iron\n"
                "• <b>3</b> – Dry clean\n"
                "• <b>4</b> – Shoe clean\n\n"
                "Reply with 1, 2, 3, or 4."
            )
        if step == "service":
            choice_map = {"1": "wash_only", "2": "wash_iron", "3": "dry_clean", "4": "shoe_clean"}
            state["service_choice"] = choice_map.get(message, "wash_only")
            state["step"] = "weight"
            _booking_state[chat_id] = state
            return (
                "How many <b>kg of clothes</b>? (e.g. 2 or 3.5)\n\n"
                "If you don't know the weight, you can send your <b>total clothes</b> instead, e.g.:\n"
                "• <b>5 shirts, 2 pants</b>\n"
                "• <b>8 pieces</b> or <b>10 clothes</b>\n\n"
                "Price is calculated per kg based on the service you chose."
            )
        if step == "weight":
            weight_kg, weight_note = _parse_weight_from_message(raw)
            if weight_kg is None:
                _booking_state[chat_id] = state
                return (
                    "Please send weight in <b>kg</b> (e.g. 2 or 3.5) or your <b>total clothes</b> "
                    "(e.g. 5 shirts, 2 pants or 8 pieces)."
                )
            if weight_kg < 0.5 or weight_kg > 100:
                _booking_state[chat_id] = state
                return "Please enter weight between 0.5 and 100 kg (or equivalent pieces)."
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
                    bill_msg = f"Got it. Estimated weight <b>{weight_kg} kg</b> (from {weight_note}). Your total bill is <b>₹{total_bill}</b>.\n\n"
                else:
                    bill_msg = f"Got it. Your total bill for <b>{weight_kg} kg</b> is <b>₹{total_bill}</b>.\n\n"
            else:
                bill_msg = "Got it.\n\n"
            return (
                bill_msg
                + "How do you want <b>pickup</b>?\n"
                "• <b>1</b> – I'll drop at outlet (you bring clothes to outlet)\n"
                "• <b>2</b> – Pickup from my address (agent will come, pick clothes, and deliver back when ready)\n\n"
                "Reply with 1 or 2."
            )
        if step == "pickup_type":
            pickup_type = "home_pickup" if message in ("2", "home", "pickup") else "self_drop"
            state["pickup_type"] = pickup_type
            if pickup_type == "home_pickup":
                state["step"] = "home_address"
                _booking_state[chat_id] = state
                return (
                    "Please send your <b>full home address</b> for pickup and delivery.\n\n"
                    "Our agent will <b>pick up</b> from this address and <b>deliver back</b> here when ready."
                )
            state["step"] = "instructions"
            _booking_state[chat_id] = state
            return (
                "Any other <b>instructions</b> for us? (e.g. delicate, no softener, specific folding)\n\n"
                "Type your message, or <b>no</b> / <b>none</b> to skip."
            )
        if step == "home_address":
            home_addr = raw.strip() if raw.strip() else ""
            if not home_addr:
                _booking_state[chat_id] = state
                return "Please send your full home address for pickup and delivery."
            state["pickup_address"] = home_addr
            state["delivery_address"] = home_addr
            state["step"] = "instructions"
            _booking_state[chat_id] = state
            return (
                "Any other <b>instructions</b> for us? (e.g. delicate, no softener, specific folding)\n\n"
                "Type your message, or <b>no</b> / <b>none</b> to skip."
            )
        if step == "instructions":
            instructions = raw.strip() if raw.strip() else ""
            if instructions and instructions.lower() in ("no", "none", "nope", "skip", "-"):
                instructions = ""
            state["customer_instructions"] = instructions
            _booking_state.pop(chat_id, None)
            address = state.get("address", "")
            pickup_type = state.get("pickup_type", "self_drop")
            # Use home address from "home_address" step when they chose pickup from home
            pickup_address = state.get("pickup_address", "") if pickup_type == "home_pickup" else ""
            delivery_address = state.get("delivery_address", "") if pickup_type == "home_pickup" else ""
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
                )
                if result.get("error") == "setup":
                    return result.get("message", "Please run the Supabase migration (see docs).")
                if result.get("error") == "no_outlets":
                    return "⚠️ " + (result.get("message") or "All outlets are currently on maintenance. Please try again later.")
                welcome = "✅ <b>Booking confirmed</b>\n\n"
                services_str = ", ".join((s.replace("_", " ").title() for s in result.get("services", [])))
                weight_line = f"{result.get('weight_kg', 1)} kg"
                if result.get("weight_note"):
                    weight_line += f" (from {result['weight_note']})"
                delivery_type_str = "Express (≈24 hrs)" if result.get("is_express") else "Standard (≈48 hrs)"
                msg = (
                    welcome
                    + "📋 <b>Booking details</b>\n"
                    + "────────────────\n"
                    + f"<b>Order ID:</b> <code>{result['order_number']}</code>\n"
                    + f"<b>Services:</b> {services_str}\n"
                    + f"<b>Weight:</b> {weight_line}\n"
                    + f"<b>Delivery:</b> {delivery_type_str}\n"
                    + f"<b>Outlet:</b> {result['outlet_name']}\n"
                    + f"<b>Expected delivery:</b> in about {result['expected_hours']} hours\n"
                    + f"<b>Total:</b> ₹{result.get('total_price', 0)}\n"
                )
                if result.get("customer_instructions"):
                    msg += f"<b>Your instructions:</b> {result['customer_instructions']}\n"
                if result.get("pickup_type") == "home_pickup":
                    msg += f"<b>Pickup & delivery address:</b>\n{result.get('pickup_address') or address}\n"
                    msg += "\nAgent will <b>pick up</b> from this address and <b>deliver back</b> when ready."
                    if result.get("is_express"):
                        msg += " Express: early pickup and drop."
                else:
                    msg += "\n<b>Drop-off:</b> You can drop your clothes/shoes at the outlet."
                if result.get("maintenance_note"):
                    msg += "\n\n⚠️ " + result["maintenance_note"]
                msg += "\n\nUse <b>Track</b> or ask \"Where is my order?\" for updates."
                msg += "\n\n⭐ <b>Rate your experience?</b> (optional) Reply with <b>1-5</b> or type <b>skip</b>."
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

    # 2) /start
    if message == "/start" or message == "start":
        return (
            "Welcome to <b>LaundryOps</b> 👕\n\n"
            "1️⃣ <b>Book</b> – Schedule a pickup\n"
            "2️⃣ <b>Track</b> – Check order status (send Order ID e.g. ORD-1234ABCD)\n"
            "3️⃣ <b>Pricing</b> – Services and fees\n"
            "4️⃣ <b>Support</b> – Policies and help\n\n"
            "You can also ask: \"Where is my order?\" or \"Kitna time lagega?\""
        )

    # 3) Order-related NL (before Book so "my order"/"my booking" don't start new book)
    if _is_order_related(message):
        return answer_order_query(chat_id, text)

    # 4) Book intent → start flow (ask name first)
    if any(w in message for w in ("book", "pickup", "schedule", "order lagana", "laundry bhejo")):
        _booking_state[chat_id] = {"step": "name"}
        return "Please send your <b>full name</b> to start the booking."

    # 5) Track by order number
    order_num = _extract_order_number(message, text)
    if order_num:
        order = get_order_by_number(order_num)
        if order:
            items_str = order.get("items_summary") or "—"
            delivery = order.get("delivery_time") or "—"
            return (
                f"📦 Order <code>{order.get('order_number')}</code>\n"
                f"Status: <b>{order.get('status', 'Unknown')}</b>\n"
                f"Services: {items_str}\n"
                f"Expected delivery: {delivery}\n"
                f"Outlet: {order.get('outlet_name', '—')}"
            )
        return f"Order <code>{order_num}</code> not found. Please check the ID."

    # 6) Track without order number
    if any(w in message for w in ("track", "status", "where is my order", "kahan hai")):
        orders = get_orders_for_customer(chat_id, limit=1)
        if not orders:
            return "Please send your <b>Order ID</b> (e.g. ORD-1234ABCD) to track, or type <b>Book</b> to schedule a pickup."
        o = get_order_by_number(orders[0]["order_number"])
        if o:
            items_str = o.get("items_summary") or "—"
            delivery = o.get("delivery_time") or "—"
            return (
                f"📦 Your latest order <code>{o.get('order_number')}</code>\n"
                f"Status: <b>{o.get('status', 'Unknown')}</b>\n"
                f"Services: {items_str}\n"
                f"Expected delivery: {delivery}\n"
                f"Outlet: {o.get('outlet_name', '—')}"
            )
        return "Please send your Order ID (e.g. ORD-1234ABCD) to track."

    # 7) Pricing / support → RAG
    if any(w in message for w in ("price", "pricing", "cost", "fee", "support", "complaint", "policy", "faq", "rewash", "delivery time", "express")):
        return answer_with_rag(text)

    # 8) Default: try RAG for general questions, else menu
    rag_reply = answer_with_rag(text)
    if rag_reply and "don't have" not in rag_reply.lower() and "no specific" not in rag_reply.lower():
        return rag_reply
    return (
        "You can: <b>Book</b>, <b>Track</b> (with Order ID), or ask about <b>pricing</b>/<b>support</b>. "
        "Or ask: \"Where is my order?\", \"Kitna time lagega?\""
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
