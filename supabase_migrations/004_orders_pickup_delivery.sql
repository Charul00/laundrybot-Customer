-- Pickup from home + delivery back. Run in Supabase SQL Editor.

-- Add columns to orders for pickup/delivery type and exact address
alter table orders
add column if not exists pickup_type text default 'self_drop';

alter table orders
add column if not exists pickup_address text;

alter table orders
add column if not exists delivery_address text;

-- Constrain pickup_type (optional; comment out if your Postgres version doesn't support add constraint on existing column)
-- alter table orders add constraint orders_pickup_type_check check (pickup_type in ('self_drop', 'home_pickup'));

comment on column orders.pickup_type is 'self_drop = customer drops at outlet; home_pickup = agent picks up from address and delivers back';
comment on column orders.pickup_address is 'Exact address for agent pickup (when pickup_type = home_pickup)';
comment on column orders.delivery_address is 'Exact address for agent drop after laundry (when pickup_type = home_pickup)';

-- Set default for existing rows
update orders set pickup_type = 'self_drop' where pickup_type is null;
