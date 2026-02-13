"""
Natural language order queries with LangChain.
User asks in free form ("kitna time lagega?", "my booking details")
→ we fetch order data from DB, then a LangChain chain turns it into a short reply.
"""
import re
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from app.config import OPENAI_API_KEY
from app.services.tracking_service import get_order_by_number, get_orders_for_customer


def _extract_order_number_from_message(message: str) -> Optional[str]:
    """Try to find ORD-xxxx in message (case insensitive)."""
    m = re.search(r"ORD-?([A-Za-z0-9]{4,})", message, re.IGNORECASE)
    if m:
        return "ORD-" + m.group(1).upper()
    return None


def _format_order_plain(order: dict) -> str:
    status = order.get("status", "Unknown")
    delivery = order.get("delivery_time") or "—"
    outlet = order.get("outlet_name") or "—"
    items = order.get("items_summary") or "—"
    return (
        f"Order {order.get('order_number', '—')}: {status}. "
        f"Services: {items}. Expected delivery: {delivery}. Outlet: {outlet}."
    )


def _get_order_reply_chain():
    """LangChain chain: order_data + user_message -> natural language reply."""
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a friendly LaundryOps assistant. The user asked about their order. "
            "Give a clear update: status, services, expected delivery, outlet. "
            "Use only the order data below. Reply in 1-3 short sentences. "
            "If they asked in Hindi/Hinglish, you may reply in the same tone.",
        ),
        ("human", "Order data:\n{order_data}\n\nUser asked: {user_message}"),
    ])
    llm = ChatOpenAI(model="gpt-4o-mini", max_tokens=120, api_key=OPENAI_API_KEY)
    return prompt | llm | StrOutputParser()


def answer_order_query(telegram_chat_id: str, user_message: str) -> str:
    """
    Resolve which order (by order number in message, or customer's recent orders),
    fetch from DB, then use LangChain chain to generate a natural-language reply.
    """
    if not OPENAI_API_KEY:
        order_num = _extract_order_number_from_message(user_message)
        if order_num:
            order = get_order_by_number(order_num)
            if order:
                return _format_order_plain(order)
        orders = get_orders_for_customer(telegram_chat_id, limit=1)
        if orders:
            o = get_order_by_number(orders[0]["order_number"])
            if o:
                return _format_order_plain(o)
        return "I couldn't find an order. Please share your Order ID (e.g. ORD-1234ABCD) to track."

    order_num = _extract_order_number_from_message(user_message)
    orders_data = []
    if order_num:
        order = get_order_by_number(order_num)
        if order:
            orders_data = [order]
    if not orders_data:
        recent = get_orders_for_customer(telegram_chat_id, limit=3)
        for r in recent:
            o = get_order_by_number(r["order_number"])
            if o:
                orders_data.append(o)

    if not orders_data:
        return (
            "I couldn't find any order for you. If you have an Order ID (e.g. ORD-1234ABCD), "
            "send it and I'll look it up. You can also type 'Book' to schedule a pickup."
        )

    data_summary = "\n".join(
        f"Order {o.get('order_number')}: status={o.get('status')}, "
        f"services={o.get('items_summary', '—')}, delivery_time={o.get('delivery_time')}, "
        f"outlet={o.get('outlet_name')}, total_price={o.get('total_price')}"
        for o in orders_data
    )

    try:
        chain = _get_order_reply_chain()
        reply = chain.invoke({"order_data": data_summary, "user_message": user_message})
        return (reply or _format_order_plain(orders_data[0])).strip()
    except Exception:
        return _format_order_plain(orders_data[0])
