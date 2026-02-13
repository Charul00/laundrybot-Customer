# Supabase setup for LaundryOps bot

Do **only** these steps in Supabase. No RLS policies or extra config are required for the bot (it uses the **service_role** key).

---

## Checklist

| # | Task | Where | Done |
|---|------|--------|-----|
| 1 | Add `telegram_chat_id` to `customers` | SQL Editor | ☐ |
| 2 | Create `match_faq_documents` RPC (for RAG) | SQL Editor | ☐ |
| 3 | (Optional) Add more FAQ content | SQL Editor – run `002_extra_faq_content.sql` | ☐ |
| 4 | Generate embeddings for `faq_documents` | Run Python script once | ☐ |
| 5 | (Optional) Pune-only: add city to outlets + areas | SQL Editor – run `003_outlets_pune_city.sql` | ☐ |
| 6 | (Optional) Pickup from home: add pickup/delivery to orders | SQL Editor – run `004_orders_pickup_delivery.sql` | ☐ |
| 7 | (Optional) Weight-based pricing: add total_weight_kg to orders | SQL Editor – run `005_orders_weight_kg.sql` | ☐ |
| 8 | (Optional) Instructions + weight note: add customer_instructions, weight_note to orders | SQL Editor – run `006_orders_instructions_weight_note.sql` | ☐ |
| 9 | (Optional) One outlet per area (Kothrud, FC Road, Kondhwa, etc.) | SQL Editor – run `007_outlets_one_per_area.sql` | ☐ |
| 10 | (Optional) Staff table + seed staff per outlet | SQL Editor – run `008_staff_table_and_seed.sql` | ☐ |
| 11 | (Optional) Insert dummy data | Run Python script once | ☐ |

---

## Step 1: Add `telegram_chat_id` to customers

1. In Supabase dashboard: **SQL Editor** → **New query**.
2. Paste and run:

```sql
alter table customers
add column if not exists telegram_chat_id text unique;

comment on column customers.telegram_chat_id is 'Telegram chat_id for bot conversations';
```

3. Click **Run**. No error = done.

---

## Step 2: Create RAG vector search function

1. **SQL Editor** → **New query**.
2. Paste and run (from `telegram-bot/supabase_migrations/001_vector_search_rpc.sql`):

```sql
create or replace function match_faq_documents(
  query_embedding text,
  match_count int default 3
)
returns table (id uuid, content text)
language plpgsql
as $$
begin
  return query
  select faq_documents.id, faq_documents.content
  from faq_documents
  where faq_documents.embedding is not null
  order by faq_documents.embedding <=> query_embedding::vector(1536)
  limit match_count;
end;
$$;
```

3. Click **Run**. No error = done.

---

## Step 3 (Optional): More FAQ content for RAG

In **SQL Editor**, run the contents of `supabase_migrations/002_extra_faq_content.sql` to add more pricing, delivery, complaint, and policy lines. Then run **Step 4** (fill embeddings) so the new rows get embeddings.

---

## Step 4: Generate embeddings for `faq_documents` (so RAG works)

Your `faq_documents` table has `content` and `embedding` (vector). If `embedding` is null, RAG returns nothing. Fill embeddings once with this script:

1. From project root:

```bash
cd "/Users/charulchim/Documents/ai assessment amber /telegram-bot"
source venv/bin/activate
python scripts/fill_faq_embeddings.py
```

2. Script will read all rows from `faq_documents`, call OpenAI for each `content`, and update the `embedding` column. Requires `.env` with `OPENAI_API_KEY` and `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`. If you added more FAQ rows (Step 3), run this script again.

---

## Step 5 (Optional): Pune-only – outlets city + areas

Run `supabase_migrations/003_outlets_pune_city.sql` in SQL Editor. It adds a `city` column to `outlets` (set to Pune) and an optional `pune_areas` table for future area-based outlet assignment. The bot already checks that the address contains "Pune" or the user types "skip".

## Step 6 (Optional): Pickup from home – orders pickup/delivery

Run `supabase_migrations/004_orders_pickup_delivery.sql` in SQL Editor. It adds `pickup_type` (self_drop / home_pickup), `pickup_address`, and `delivery_address` to `orders`. Required if you use "Pickup from my address" (agent picks up and delivers back).

## Step 7 (Optional): Weight-based pricing – orders total_weight_kg

Run `supabase_migrations/005_orders_weight_kg.sql` in SQL Editor. It adds `total_weight_kg` to `orders`. The bot asks "How many kg of clothes?" (or total clothes, e.g. "5 shirts, 2 pants" or "8 pieces") and calculates price as **weight × rate per kg** (services table `base_price` = rate per kg). Required for the weight step in booking.

## Step 8 (Optional): Instructions + weight note – orders customer_instructions, weight_note

Run `supabase_migrations/006_orders_instructions_weight_note.sql` in SQL Editor. It adds `customer_instructions` (any other instructions from the customer) and `weight_note` (e.g. "5 shirts, 2 pants" when weight was estimated from pieces). Required for the "Any other instructions?" step and for showing piece-based weight in the order.

## Step 9 (Optional): One outlet per area

Run `supabase_migrations/007_outlets_one_per_area.sql` in SQL Editor. It creates **one outlet per Pune area** (e.g. LaundryOps - Kothrud, LaundryOps - FC Road, LaundryOps - Kondhwa, Viman Nagar, Baner, Wakad, etc.) and links each area in `pune_areas` to its outlet. So you get as many outlets as locations (Kothrud, Hinjewadi, Viman Nagar, FC Road, Camp, Aundh, Baner, Pimple Saudagar, Wakad, Hadapsar, Kondhwa, Shivajinagar, Deccan, Karve Road, Sinhagad Road, Koregaon Park, MG Road, SB Road, JM Road). The admin dashboard and bot will show all of them.

## Step 10 (Optional): Staff table and seed data

Run `supabase_migrations/008_staff_table_and_seed.sql` in SQL Editor. It creates the `staff` table (full_name, role, outlet_id, phone_number, is_active) and seeds **one Manager and one Operator per outlet** so the admin dashboard Staff page shows data. You can edit staff in Supabase Table Editor after.

## Step 11 (Optional): Dummy data

To test **Track**, **Where is my order?**, and analytics, you can add sample customers and orders (run from `telegram-bot` with venv active):

```bash
cd "/Users/charulchim/Documents/ai assessment amber /telegram-bot"
source venv/bin/activate
python scripts/seed_dummy_data.py
```

This will:
- Use your existing **outlets** and **services**.
- Insert sample **customers** (no Telegram link by default).
- Insert sample **orders** with **order_items** and **order_status_logs**.
- Insert sample **feedback**.

You can still **Book** from the bot to create real customers/orders; dummy data is only for testing tracking and “my order” queries when you don’t have real orders yet.

---

## If booking says "telegram_chat_id does not exist"

Run **Step 1** in Supabase SQL Editor (add the column). Until that is done, Book will show a setup message with the exact `ALTER TABLE` command.

## What you do **not** need to do

- **RLS policies** – Bot uses service_role; no need to change policies for the bot.
- **Auth / sign-in** – Not used by the bot.
- **Realtime** – Not used by the bot.
- **Storage** – Not used by the bot.
- **Edge Functions** – Not required for this project.

---

## Quick verify in Supabase

After Step 1 and 2:

- **Table Editor** → `customers` → columns should include `telegram_chat_id`.
- **SQL Editor** → run:
  ```sql
  select routine_name from information_schema.routines where routine_name = 'match_faq_documents';
  ```
  One row = RPC exists.

After Step 4:

- **Table Editor** → `faq_documents` → rows should have non-null `embedding` after running the script.
