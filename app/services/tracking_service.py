"""
Get order status by order_number or by customer (telegram_chat_id).
"""
from typing import Optional

from app.db.supabase_client import get_supabase


def get_order_by_number(order_number: str) -> Optional[dict]:
    """
    Normalize order_number (e.g. ORD-1234 or ord-1234), fetch order + latest status.
    Returns None if not found, else dict with order_number, status, delivery_time, outlet_name, etc.
    """
    supabase = get_supabase()
    normalized = order_number.strip().upper()
    if not normalized.startswith("ORD-"):
        normalized = "ORD-" + normalized if normalized else ""

    r = (
        supabase.table("orders")
        .select(
            "id, order_number, status, delivery_time, total_price, priority_type, outlet_id, created_at"
        )
        .eq("order_number", normalized)
        .limit(1)
        .execute()
    )
    if not r.data or len(r.data) == 0:
        return None

    row = r.data[0]
    outlet_id = row.get("outlet_id")
    outlet_name = ""
    if outlet_id:
        o = supabase.table("outlets").select("outlet_name").eq("id", outlet_id).single().execute()
        if o.data:
            outlet_name = o.data.get("outlet_name", "")

    logs = (
        supabase.table("order_status_logs")
        .select("status, updated_at")
        .eq("order_id", row["id"])
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    status = row.get("status") or (logs.data[0]["status"] if logs.data else "Unknown")

    # Order items (service names) for "my order" / track reply
    items_r = (
        supabase.table("order_items")
        .select("service_id")
        .eq("order_id", row["id"])
        .execute()
    )
    items_summary = "—"
    if items_r.data:
        service_ids = [x["service_id"] for x in items_r.data]
        names = []
        for sid in service_ids:
            s = supabase.table("services").select("service_name").eq("id", sid).limit(1).execute()
            if s.data and s.data[0].get("service_name"):
                names.append(s.data[0]["service_name"].replace("_", " ").title())
        items_summary = ", ".join(names) if names else "—"

    return {
        "order_number": row["order_number"],
        "status": status,
        "delivery_time": row.get("delivery_time"),
        "total_price": row.get("total_price"),
        "priority_type": row.get("priority_type"),
        "outlet_name": outlet_name,
        "created_at": row.get("created_at"),
        "items_summary": items_summary,
    }


def get_orders_for_customer(telegram_chat_id: str, limit: int = 5) -> list[dict]:
    """Get recent orders for customer linked to this telegram_chat_id."""
    supabase = get_supabase()
    c = (
        supabase.table("customers")
        .select("id")
        .eq("telegram_chat_id", telegram_chat_id)
        .limit(1)
        .execute()
    )
    if not c.data or len(c.data) == 0:
        return []

    customer_id = c.data[0]["id"]
    r = (
        supabase.table("orders")
        .select("id, order_number, status, delivery_time, created_at")
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return r.data or []
