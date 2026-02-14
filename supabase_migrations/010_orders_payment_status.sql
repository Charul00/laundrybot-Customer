-- Add payment method to orders (fake for dev; no real integration yet)
-- Values: "Cash on delivery", "UPI", "Online"
alter table orders
  add column if not exists payment_status text;

comment on column orders.payment_status is 'Display: Cash on delivery, UPI, or Online (fake for dev)';
