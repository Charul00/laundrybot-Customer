"""
One-time script: insert dummy customers, orders, order_items, order_status_logs, feedback.
Uses existing outlets and services. Run from telegram-bot:  python scripts/seed_dummy_data.py
Requires .env: SUPABASE_URL, SUPABASE_SERVICE_KEY
"""
import sys
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.db.supabase_client import get_supabase


STATUSES = ["Received", "Washing", "Drying", "Ironing", "Ready", "Delivered"]
CUSTOMER_TYPES = ["student", "professional", "family"]
PRIORITIES = ["normal", "premium", "express"]
CLOTH_TYPES = ["Cotton", "Wool", "Silk", "Bedding", "Shoes"]
FIRST_NAMES = ["Rahul", "Priya", "Amit", "Neha", "Vikram", "Kavita", "Sanjay", "Anita", "Raj", "Pooja"]
LAST_NAMES = ["Sharma", "Patel", "Kumar", "Singh", "Gupta", "Reddy", "Nair", "Mehta"]


def order_number():
    return "ORD-" + uuid.uuid4().hex[:8].upper()


def main():
    supabase = get_supabase()

    outlets = supabase.table("outlets").select("id").eq("is_active", True).execute()
    if not outlets.data or len(outlets.data) == 0:
        print("No outlets found. Add outlets first in Supabase.")
        return
    outlet_ids = [o["id"] for o in outlets.data]

    services = supabase.table("services").select("id, base_price").execute()
    if not services.data or len(services.data) == 0:
        print("No services found. Add services first in Supabase.")
        return
    service_ids = [s["id"] for s in services.data]
    service_prices = {s["id"]: float(s["base_price"]) for s in services.data}

    # 1) Customers (~100)
    print("Inserting customers...")
    customer_ids = []
    for i in range(100):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        phone = "98765" + str(10000 + i).zfill(5)  # unique per run
        try:
            r = supabase.table("customers").insert({
                "full_name": f"{first} {last}",
                "phone_number": phone,
                "email": f"{first.lower()}.{last.lower()}{i}@example.com" if i % 3 == 0 else None,
                "customer_type": random.choice(CUSTOMER_TYPES),
                "address": f"{100 + i} Street, Pune",
                "loyalty_points": random.randint(0, 50),
                "total_orders": 0,
            }).execute()
            if r.data:
                customer_ids.append(r.data[0]["id"])
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                pass  # skip duplicate phone
            else:
                print(f"Customer insert error: {e}")
    print(f"  -> {len(customer_ids)} customers")

    if not customer_ids:
        print("No customers inserted. Check if table already has data or constraints.")
        return

    # 2) Orders (~400) + order_items + order_status_logs + some feedback
    print("Inserting orders, order_items, status logs, feedback...")
    orders_created = 0
    for i in range(400):
        cid = random.choice(customer_ids)
        oid = random.choice(outlet_ids)
        priority = random.choice(PRIORITIES)
        status = random.choice(STATUSES)
        now = datetime.utcnow() - timedelta(days=random.randint(0, 30))
        delivery = now + timedelta(hours=24 + random.randint(0, 48))
        total = round(random.uniform(100, 800), 2)
        express_fee = 0 if priority != "express" else round(total * 0.3, 2)
        try:
            ord_r = supabase.table("orders").insert({
                "order_number": order_number(),
                "customer_id": cid,
                "outlet_id": oid,
                "priority_type": priority,
                "status": status,
                "delivery_time": delivery.isoformat(),
                "total_price": total,
                "express_fee": express_fee,
                "payment_status": random.choice(["pending", "paid"]),
            }).execute()
            if not ord_r.data:
                continue
            order_id = ord_r.data[0]["id"]
            orders_created += 1

            # order_items (1–3 per order)
            n_items = random.randint(1, 3)
            for _ in range(n_items):
                sid = random.choice(service_ids)
                qty = random.randint(1, 3)
                price = service_prices.get(sid, 50) * qty
                supabase.table("order_items").insert({
                    "order_id": order_id,
                    "service_id": sid,
                    "cloth_type": random.choice(CLOTH_TYPES),
                    "quantity": qty,
                    "price": price,
                }).execute()

            # one status log
            supabase.table("order_status_logs").insert({
                "order_id": order_id,
                "status": status,
            }).execute()

            # feedback for ~25%
            if random.random() < 0.25:
                supabase.table("feedback").insert({
                    "order_id": order_id,
                    "rating": random.randint(1, 5),
                    "category": random.choice(["quality", "delivery", "service"]),
                    "comment": "Good service" if random.random() > 0.5 else None,
                }).execute()
        except Exception as e:
            print(f"  Order insert error: {e}")

    print(f"  -> {orders_created} orders (with items, logs, and some feedback)")
    print("Done. You can now use Track / 'Where is my order?' with existing order numbers from Supabase Table Editor (orders.order_number).")


if __name__ == "__main__":
    main()
