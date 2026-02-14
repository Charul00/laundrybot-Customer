"""
Deterministic booking: create/update customer, create order with items, assign outlet.
Collects: name, address, phone, delivery (express/standard), service type, weight (kg or pieces), instructions.
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from app.db.supabase_client import get_supabase

# Map our flow options to service_name in DB (services table)
SERVICE_MAP = {
    "wash_only": ["wash"],
    "wash_iron": ["wash", "iron"],
    "dry_clean": ["dry_clean"],
    "shoe_clean": ["shoe_clean"],
    "home_textiles": ["home_textiles"],  # bedsheet, carpet, curtains
    "premium_iron": ["premium_iron"],     # premium care ironing
    "press_iron": ["press_iron"],         # press iron
    "steam_iron": ["steam_iron"],         # steam iron
}


def _next_order_number() -> str:
    return "ORD-" + str(uuid.uuid4().hex)[:8].upper()


def _assign_outlet(supabase) -> str:
    r = supabase.table("outlets").select("id").eq("is_active", True).execute()
    if not r.data or len(r.data) == 0:
        raise ValueError("No active outlets found")
    return r.data[0]["id"]


# Fallback Pune area names if DB unavailable (e.g. Viman Nagar is in Pune but doesn't contain "pune")
_PUNE_AREAS_FALLBACK = [
    "pune", "viman nagar", "kothrud", "hinjewadi", "fc road", "camp", "aundh", "baner",
    "pimple saudagar", "wakad", "hadapsar", "kondhwa", "shivajinagar", "deccan", "karve road",
    "sinhagad road", "koregaon park", "mg road", "sb road", "jm road",
]


def _get_pune_area_names(supabase) -> list:
    """Return list of lowercase Pune area names from pune_areas table."""
    try:
        r = supabase.table("pune_areas").select("area_name").execute()
        if r.data:
            return [(row.get("area_name") or "").strip().lower() for row in r.data if row.get("area_name")]
    except Exception:
        pass
    return _PUNE_AREAS_FALLBACK


def is_pune_address(address: str) -> bool:
    """True if address is in Pune: contains 'pune' or any known Pune area (e.g. Viman Nagar, Kothrud)."""
    if not (address or "").strip():
        return False
    raw = address.strip().lower()
    if raw == "skip":
        return False  # Skip is not a valid address; user must send area or full address
    if "pune" in raw:
        return True
    try:
        supabase = get_supabase()
        areas = _get_pune_area_names(supabase)
        for area in areas:
            if area and area in raw:
                return True
    except Exception:
        for area in _PUNE_AREAS_FALLBACK:
            if area and area in raw:
                return True
    return False


def get_nearby_outlets_message() -> str:
    """Return a line like 'Your nearby outlets: Outlet A (Kothrud), Outlet B (FC Road) (on maintenance), ...'.
    Lists outlets by area (from pune_areas) so the user sees which areas we serve and which outlets are on maintenance,
    even before entering their address."""
    try:
        supabase = get_supabase()
        r = supabase.table("pune_areas").select("area_name, outlet_id").execute()
        if not r.data:
            return "We serve Pune (Kothrud, Hinjewadi, Viman Nagar, and more)."
        if r.data:
            outlet_names = {}
            outlet_active = {}
            for row in r.data:
                oid = row.get("outlet_id")
                if oid and oid not in outlet_names:
                    o = supabase.table("outlets").select("outlet_name, is_active").eq("id", oid).limit(1).execute()
                    if o.data:
                        outlet_names[oid] = o.data[0].get("outlet_name") or "Outlet"
                        outlet_active[oid] = o.data[0].get("is_active", True) is True
            parts = []
            for row in r.data:
                area = (row.get("area_name") or "").strip()
                oid = row.get("outlet_id")
                if area and oid:
                    name = outlet_names.get(oid, "Outlet")
                    suffix = " (on maintenance)" if not outlet_active.get(oid, True) else ""
                    parts.append(f"{name} ({area}){suffix}")
            if parts:
                return "Your nearby outlets (by area; we assign by your address): " + ", ".join(parts[:10]) + "."
        # Fallback: list areas only
        areas = _get_pune_area_names(get_supabase())
        if areas:
            return "Your nearby areas (Pune): " + ", ".join(a.title() for a in areas[:10]) + "."
    except Exception:
        pass
    return "We serve Pune (Kothrud, Hinjewadi, Viman Nagar, and more)."


def get_nearby_outlet_for_address(address: str) -> Optional[Tuple[str, str, bool]]:
    """
    If the address contains a known Pune area (e.g. "kg road pg society kothrud" -> Kothrud),
    return (area_name, outlet_name, is_active). Otherwise return None.
    Used to tell the customer "Your nearby store is LaundryOps - Kothrud (Kothrud)."
    """
    if not (address or "").strip():
        return None
    address_lower = address.strip().lower()
    try:
        supabase = get_supabase()
        r = supabase.table("pune_areas").select("area_name, outlet_id").execute()
        if not r.data:
            return None
        for row in r.data:
            area_name = (row.get("area_name") or "").strip()
            area_lower = area_name.lower()
            if area_lower and area_lower in address_lower:
                oid = row.get("outlet_id")
                if not oid:
                    return (area_name, area_name, True)
                o = supabase.table("outlets").select("outlet_name, is_active").eq("id", oid).limit(1).execute()
                if o.data:
                    outlet_name = o.data[0].get("outlet_name") or area_name
                    is_active = o.data[0].get("is_active", True) is True
                    return (area_name, outlet_name, is_active)
                return (area_name, area_name, True)
    except Exception:
        pass
    return None


def _assign_outlet_by_address(supabase, address: str) -> Tuple[str, Optional[str]]:
    """
    If address contains a known Pune area and that area has an *active* outlet, use it.
    If that outlet is on maintenance (is_active=False), assign another active outlet and return a note.
    Returns (outlet_id, maintenance_note). maintenance_note is None unless we fell back due to maintenance.
    """
    if not (address or "").strip():
        return _assign_outlet(supabase), None
    address_lower = address.strip().lower()
    try:
        areas = supabase.table("pune_areas").select("area_name, outlet_id").execute()
        if areas.data:
            for row in areas.data:
                area_name = (row.get("area_name") or "").strip().lower()
                outlet_id = row.get("outlet_id")
                if area_name and outlet_id and area_name in address_lower:
                    out = supabase.table("outlets").select("outlet_name, is_active").eq("id", outlet_id).limit(1).execute()
                    if out.data:
                        is_active = out.data[0].get("is_active", True) is True
                        if is_active:
                            return outlet_id, None
                        maintenance_outlet_name = out.data[0].get("outlet_name") or "Your nearest outlet"
                    else:
                        maintenance_outlet_name = "Your nearest outlet"
                    fallback_id = _assign_outlet(supabase)
                    fallback_row = supabase.table("outlets").select("outlet_name").eq("id", fallback_id).limit(1).execute()
                    fallback_name = (fallback_row.data[0].get("outlet_name", "another outlet") if fallback_row.data and len(fallback_row.data) > 0 else "another outlet")
                    note = f"That outlet ({maintenance_outlet_name}) is currently on maintenance. We've assigned your order to {fallback_name} instead."
                    return fallback_id, note
    except Exception:
        pass
    return _assign_outlet(supabase), None


def _get_service_ids(supabase, service_names: list) -> list:
    """Return list of (service_id, price_per_kg) for each service_name. base_price in DB = rate per kg."""
    out = []
    for name in service_names:
        r = supabase.table("services").select("id, base_price").eq("service_name", name).limit(1).execute()
        if r.data and len(r.data) > 0:
            out.append((r.data[0]["id"], float(r.data[0].get("base_price") or 0)))
    return out


def estimate_price(service_choice: str, weight_kg: float, delivery_type: str) -> Optional[float]:
    """
    Estimate total bill for given service, weight (kg), and delivery type.
    Returns total price (incl. +30% if express) or None if DB/rates unavailable.
    """
    try:
        supabase = get_supabase()
        service_names = SERVICE_MAP.get((service_choice or "").strip().lower(), ["wash"])
        service_rows = _get_service_ids(supabase, service_names)
        if not service_rows:
            service_rows = _get_service_ids(supabase, ["wash"])
        weight_kg = max(0.5, min(100.0, float(weight_kg or 1.0)))
        total = weight_kg * sum(rate for _, rate in service_rows)
        if (delivery_type or "").strip().lower() in ("express", "1", "2"):
            total += round(total * 0.3, 2)
        return round(total, 2)
    except Exception:
        return None


# Fake UPI ID for dev (no real payment integration yet)
FAKE_UPI_ID = "laundryops@paytm"

def create_booking(
    telegram_chat_id: str,
    full_name: str,
    address: str,
    phone: str,
    delivery_type: str,
    service_choice: str,
    weight_kg: float = 1.0,
    weight_note: Optional[str] = None,
    customer_instructions: str = "",
    pickup_type: str = "self_drop",
    pickup_address: str = "",
    delivery_address: str = "",
    payment_method: str = "cod",
    preferred_pickup_at: Optional[str] = None,
    preferred_delivery_at: Optional[str] = None,
) -> dict:
    """
    delivery_type: "express" | "standard"
    service_choice: "wash_only" | "wash_iron" | "dry_clean" | "shoe_clean" | "home_textiles" | "premium_iron" | "press_iron" | "steam_iron"
    weight_kg: total clothes weight in kg; price = weight_kg × sum(rate per kg for selected services)
    weight_note: when weight was estimated from pieces, e.g. "5 shirts, 2 pants"
    customer_instructions: any other instructions from customer (e.g. delicate, no softener)
    pickup_type: "self_drop" (customer drops at outlet) | "home_pickup" (agent picks up and delivers back)
    pickup_address, delivery_address: exact location when home_pickup (required for express + home_pickup)
    payment_method: "cod" | "upi" | "online" (fake for dev; no real integration yet)
    """
    supabase = get_supabase()
    phone_clean = "".join(c for c in phone if c.isdigit()).strip() or phone.strip()
    if not phone_clean:
        phone_clean = f"tg-{telegram_chat_id}"

    is_express = (delivery_type or "").strip().lower() in ("express", "1", "2")
    estimated_hours = 24 if is_express else 48
    express_fee = 0.0
    priority_type = "express" if is_express else "normal"

    try:
        existing = (
            supabase.table("customers")
            .select("id")
            .eq("phone_number", phone_clean)
            .limit(1)
            .execute()
        )
        if not existing.data or len(existing.data) == 0:
            existing = (
                supabase.table("customers")
                .select("id")
                .eq("telegram_chat_id", telegram_chat_id)
                .limit(1)
                .execute()
            )

        is_existing_customer = False
        if existing.data and len(existing.data) > 0:
            customer_id = existing.data[0]["id"]
            is_existing_customer = True
            supabase.table("customers").update({
                "full_name": (full_name or "").strip() or existing.data[0].get("full_name"),
                "telegram_chat_id": telegram_chat_id,
                "address": address,
            }).eq("id", customer_id).execute()
        else:
            ins = supabase.table("customers").insert({
                "full_name": (full_name or "").strip() or f"Customer {phone_clean[-4:]}",
                "phone_number": phone_clean,
                "customer_type": "professional",
                "address": address,
                "telegram_chat_id": telegram_chat_id,
            }).execute()
            customer_id = ins.data[0]["id"]

    except Exception as e:
        err = str(e).lower()
        if "telegram_chat_id" in err and ("does not exist" in err or "42703" in err):
            return {
                "error": "setup",
                "message": (
                    "Database setup needed: please add the telegram_chat_id column in Supabase. "
                    "In Supabase → SQL Editor, run: ALTER TABLE customers ADD COLUMN telegram_chat_id TEXT UNIQUE;"
                ),
            }
        raise

    try:
        outlet_id, maintenance_note = _assign_outlet_by_address(supabase, address)
    except ValueError as e:
        if "No active outlets" in str(e):
            return {
                "error": "no_outlets",
                "message": "All outlets are currently on maintenance. Please try again later.",
            }
        raise
    outlet_row = supabase.table("outlets").select("outlet_name").eq("id", outlet_id).single().execute()
    outlet_name = outlet_row.data.get("outlet_name", "Laundry Central") if outlet_row.data else "Laundry Central"

    service_names = SERVICE_MAP.get((service_choice or "").strip().lower(), ["wash"])
    service_rows = _get_service_ids(supabase, service_names)
    if not service_rows:
        service_rows = _get_service_ids(supabase, ["wash"])

    # Price = weight_kg × sum(rate per kg for each service). base_price in DB = rate per kg.
    weight_kg = max(0.5, min(100.0, float(weight_kg or 1.0)))
    total_price = weight_kg * sum(rate_per_kg for _, rate_per_kg in service_rows)
    if is_express:
        express_fee = round(total_price * 0.3, 2)
        total_price += express_fee

    order_number = _next_order_number()
    delivery_estimate = (datetime.utcnow() + timedelta(hours=estimated_hours)).replace(microsecond=0)

    pt = (pickup_type or "self_drop").strip().lower() or "self_drop"
    if pt not in ("self_drop", "home_pickup"):
        pt = "self_drop"
    pa = (pickup_address or "").strip() or None
    da = (delivery_address or "").strip() or None

    payment_display = {"cod": "Cash on delivery", "upi": "UPI", "online": "Online"}.get(
        (payment_method or "cod").strip().lower(), "Cash on delivery"
    )
    order_payload = {
        "order_number": order_number,
        "customer_id": customer_id,
        "outlet_id": outlet_id,
        "priority_type": priority_type,
        "status": "Received",
        "total_price": round(total_price, 2),
        "express_fee": round(express_fee, 2),
        "payment_status": payment_display,
        "delivery_time": delivery_estimate.isoformat(),
    }
    instructions_str = (customer_instructions or "").strip() or None
    weight_note_str = (weight_note or "").strip() or None
    preferred_pickup = (preferred_pickup_at or "").strip() or None
    preferred_delivery = (preferred_delivery_at or "").strip() or None
    order_payload_ext = {
        **order_payload,
        "pickup_type": pt,
        "pickup_address": pa,
        "delivery_address": da,
        "total_weight_kg": round(weight_kg, 2),
        "customer_instructions": instructions_str,
        "weight_note": weight_note_str,
        "preferred_pickup_at": preferred_pickup,
        "preferred_delivery_at": preferred_delivery,
    }
    try:
        order_ins = supabase.table("orders").insert(order_payload_ext).execute()
    except Exception:
        fallback = {k: v for k, v in order_payload_ext.items()
                    if k not in ("total_weight_kg", "customer_instructions", "weight_note", "preferred_pickup_at", "preferred_delivery_at")}
        try:
            order_ins = supabase.table("orders").insert(fallback).execute()
        except Exception:
            order_ins = supabase.table("orders").insert(order_payload).execute()
    order_id = order_ins.data[0]["id"]

    for sid, rate_per_kg in service_rows:
        line_price = round(rate_per_kg * weight_kg, 2)
        supabase.table("order_items").insert({
            "order_id": order_id,
            "service_id": sid,
            "quantity": 1,
            "price": line_price,
        }).execute()

    supabase.table("order_status_logs").insert({
        "order_id": order_id,
        "status": "Received",
    }).execute()

    cur = supabase.table("customers").select("total_orders").eq("id", customer_id).single().execute()
    if cur.data:
        n = (cur.data.get("total_orders") or 0) + 1
        supabase.table("customers").update({"total_orders": n}).eq("id", customer_id).execute()

    return {
        "order_number": order_number,
        "expected_hours": estimated_hours,
        "outlet_name": outlet_name,
        "order_id": order_id,
        "services": service_names,
        "weight_kg": round(weight_kg, 2),
        "weight_note": weight_note_str,
        "customer_instructions": instructions_str or "",
        "total_price": round(total_price, 2),
        "express_fee": round(express_fee, 2),
        "is_existing": is_existing_customer,
        "pickup_type": pt,
        "pickup_address": pa or "",
        "delivery_address": da or "",
        "is_express": is_express,
        "delivery_time_iso": delivery_estimate.isoformat(),
        "maintenance_note": maintenance_note,
        "payment_method": (payment_method or "cod").strip().lower(),
        "preferred_pickup_at": preferred_pickup,
        "preferred_delivery_at": preferred_delivery,
    }
