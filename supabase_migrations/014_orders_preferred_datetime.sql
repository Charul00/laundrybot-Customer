-- Preferred pickup/delivery date and time (customer choice). Run in Supabase SQL Editor.

alter table orders
  add column if not exists preferred_pickup_at text;

alter table orders
  add column if not exists preferred_delivery_at text;

comment on column orders.preferred_pickup_at is 'Customer preferred pickup date/time (e.g. Tomorrow 10am, 15 Feb 2-4pm)';
comment on column orders.preferred_delivery_at is 'Customer preferred delivery date/time';
