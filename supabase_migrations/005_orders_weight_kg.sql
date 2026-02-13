-- Store total clothes weight (kg) for price calculation. Run in Supabase SQL Editor.

alter table orders
add column if not exists total_weight_kg numeric;

comment on column orders.total_weight_kg is 'Total weight of clothes in kg; price = rate per kg × weight';

-- Optional: set default for existing rows (e.g. 1 kg)
-- update orders set total_weight_kg = 1 where total_weight_kg is null;
