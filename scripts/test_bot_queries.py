"""
Test bot query understanding and answers. Run from telegram-bot with venv active:
  python scripts/test_bot_queries.py

Uses a fake chat_id so Track/order queries may return "no order" unless you have data.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.services import chatbot_service

# Fake chat_id for testing (no real orders linked). State cleared between queries so each is independent.
TEST_CHAT_ID = "999000111"

QUERIES = [
    # Start & menu
    ("/start", "Start menu"),
    ("start", "Start (no slash)"),
    ("hi", "Greeting"),
    ("hello", "Greeting"),
    # Book intent
    ("Book", "Book – should ask name"),
    ("I want to schedule a pickup", "Book – natural"),
    ("laundry bhejo", "Book – Hinglish"),
    # Track (no order – will ask for ID or say no order)
    ("Track", "Track – no order"),
    ("track ORD-678D45BC", "Track – with sample ID"),
    ("Where is my order?", "NL – my order"),
    ("kitna time lagega?", "NL – time (Hinglish)"),
    ("Tell me about my booking", "NL – booking details"),
    ("mera order kahan hai", "NL – Hinglish"),
    ("What is the status of my order?", "NL – status"),
    # Pricing / RAG
    ("Pricing", "Pricing"),
    ("What is the cost of dry clean?", "Pricing – specific"),
    ("Do you offer same day delivery?", "RAG – express"),
    ("Is rewash free?", "RAG – rewash policy"),
    ("How much for shoe cleaning?", "RAG – shoe"),
    ("Express delivery fee", "RAG – express"),
    ("complaint", "Support – complaint"),
    ("payment options", "RAG – payment"),
    # Edge / complex
    ("I need my clothes washed and ironed by tomorrow", "Complex – book + express"),
    ("Can I get order ORD-12345678 status?", "Track – with ID in sentence"),
    ("thanks", "Thanks – fallback"),
    ("random stuff xyz", "Random – fallback"),
    # Address / Pune (when in booking flow we test separately below)
    ("pickup from home", "Book – pickup from home phrase"),
    ("do you pick up from address?", "RAG / general"),
]

# Simulated booking flow: run as one sequence with state (one chat_id, no clear between steps)
BOOKING_FLOW_QUERIES = [
    ("Book", "1. Book"),
    ("Test User", "2. Name"),
    ("123 MG Road Mumbai", "3. Random address (non-Pune) – expect Pune message"),
    ("Viman Nagar", "4. Valid Pune area – then ask phone"),
    ("9876543210", "5. Phone"),
    ("1", "6. Standard delivery"),
    ("2", "7. Wash + Iron"),
    ("5 shirts 2 pants", "7b. Weight from pieces"),
    ("1", "8. Self drop at outlet"),
    ("no", "9. No extra instructions"),
]


def main():
    print("=" * 60)
    print("LaundryOps Bot – All queries test (state cleared per query)")
    print("=" * 60)
    for i, (query, label) in enumerate(QUERIES, 1):
        try:
            chatbot_service._booking_state.pop(TEST_CHAT_ID, None)
            reply = chatbot_service.handle_message(TEST_CHAT_ID, query)
            reply_preview = (reply[:120] + "…") if len(reply) > 120 else reply
            reply_preview = reply_preview.replace("\n", " ")
            print(f"\n[{i}] {label}")
            print(f"    IN:  {query}")
            print(f"    OUT: {reply_preview}")
        except Exception as e:
            print(f"\n[{i}] {label}")
            print(f"    IN:  {query}")
            print(f"    ERR: {e}")

    print("\n" + "=" * 60)
    print("Booking flow test (random address, then skip; full flow to self-drop)")
    print("=" * 60)
    chatbot_service._booking_state.pop(TEST_CHAT_ID, None)
    for i, (query, label) in enumerate(BOOKING_FLOW_QUERIES, 1):
        try:
            reply = chatbot_service.handle_message(TEST_CHAT_ID, query)
            reply_preview = (reply[:150] + "…") if len(reply) > 150 else reply
            reply_preview = reply_preview.replace("\n", " ")
            print(f"\n[Flow {i}] {label}")
            print(f"    IN:  {query}")
            print(f"    OUT: {reply_preview}")
        except Exception as e:
            print(f"\n[Flow {i}] {label}")
            print(f"    IN:  {query}")
            print(f"    ERR: {e}")
    chatbot_service._booking_state.pop(TEST_CHAT_ID, None)

    print("\n" + "=" * 60)
    print("Done. All queries + one full booking flow (random address → skip → self drop).")
    print("For real orders / Track, test in Telegram with your chat.")


if __name__ == "__main__":
    main()
