-- Customer instructions and weight note (e.g. "5 shirts, 2 pants" when estimated). Run in Supabase SQL Editor.

alter table orders
add column if not exists customer_instructions text;

alter table orders
add column if not exists weight_note text;

comment on column orders.customer_instructions is 'Any other instructions from customer (e.g. delicate, no softener)';
comment on column orders.weight_note is 'When weight was estimated from pieces: e.g. "5 shirts, 2 pants" or "8 pieces"';
