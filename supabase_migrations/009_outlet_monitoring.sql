-- Outlet monitoring: electricity, detergent, and running orders are shown per outlet in the admin dashboard.
-- Run in Supabase SQL Editor after 007_outlets_one_per_area.sql.

-- Add monitoring columns to outlets (usage can be updated manually or by an external system)
alter table outlets
  add column if not exists electricity_usage_kwh numeric default 0,
  add column if not exists detergent_usage_kg numeric default 0;

comment on column outlets.electricity_usage_kwh is 'Electricity usage in kWh (e.g. current month or total). Update via Table Editor or API.';
comment on column outlets.detergent_usage_kg is 'Detergent usage in kg (e.g. current month or total). Update via Table Editor or API.';

-- Seed random sample values per outlet (electricity 50–500 kWh, detergent 5–80 kg)
update outlets
set
  electricity_usage_kwh = round((random() * 450 + 50)::numeric, 2),
  detergent_usage_kg = round((random() * 75 + 5)::numeric, 2);
