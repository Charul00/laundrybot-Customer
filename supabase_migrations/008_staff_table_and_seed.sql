-- Staff table and seed data. Run in Supabase SQL Editor.
-- role must be one of: washer, ironer, manager, delivery (staff_role_check)

-- 1) Create staff table (if not exists; your DB may already have it with staff_role_check)
create table if not exists staff (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  role text check (role in ('washer', 'ironer', 'manager', 'delivery')),
  outlet_id uuid references outlets(id),
  phone_number text,
  is_active boolean default true,
  created_at timestamp default now()
);

comment on table staff is 'Staff per outlet for owner dashboard';
comment on column staff.role is 'washer, ironer, manager, delivery';

-- 2) Seed staff: one manager per outlet (for outlets with no staff yet)
insert into staff (full_name, role, outlet_id, phone_number, is_active)
select
  'Manager - ' || replace(o.outlet_name, 'LaundryOps - ', ''),
  'manager',
  o.id,
  '98765' || lpad((row_number() over (order by o.outlet_name))::text, 5, '0'),
  true
from outlets o
where o.is_active = true
  and not exists (select 1 from staff s where s.outlet_id = o.id);

-- 3) Add one washer per outlet that has only a manager
insert into staff (full_name, role, outlet_id, phone_number, is_active)
select
  'Washer - ' || replace(o.outlet_name, 'LaundryOps - ', ''),
  'washer',
  o.id,
  '98766' || lpad((row_number() over (order by o.outlet_name))::text, 5, '0'),
  true
from outlets o
where o.is_active = true
  and (select count(*) from staff s where s.outlet_id = o.id) = 1
  and not exists (select 1 from staff s2 where s2.outlet_id = o.id and s2.role = 'washer');
