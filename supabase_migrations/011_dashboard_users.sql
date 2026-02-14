-- Dashboard login: owner (all outlets) and manager (per-outlet).
-- Run this in Supabase SQL Editor (same project as admin dashboard).

create table if not exists dashboard_users (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  password_hash text not null,
  role text not null check (role in ('owner', 'manager')),
  outlet_id uuid references outlets(id),
  created_at timestamptz default now(),
  unique (email, outlet_id)
);

comment on column dashboard_users.role is 'owner = see all outlets; manager = one outlet only';
comment on column dashboard_users.outlet_id is 'null for owner; required for manager';

create index if not exists dashboard_users_email_idx on dashboard_users(email);
create index if not exists dashboard_users_outlet_idx on dashboard_users(outlet_id);

-- Seed: one owner (password: owner123), one manager per outlet (password: manager123).
-- Password hash = encode(digest(plain, 'sha256'), 'hex'). App hashes the same way for comparison.
insert into dashboard_users (email, password_hash, role, outlet_id)
select
  'owner@laundryops.com',
  encode(digest('owner123', 'sha256'), 'hex'),
  'owner',
  null
where not exists (select 1 from dashboard_users where email = 'owner@laundryops.com' limit 1);

insert into dashboard_users (email, password_hash, role, outlet_id)
select
  'manager@laundryops.com',
  encode(digest('manager123', 'sha256'), 'hex'),
  'manager',
  o.id
from outlets o
where not exists (
  select 1 from dashboard_users d where d.outlet_id = o.id and d.role = 'manager' limit 1
);
