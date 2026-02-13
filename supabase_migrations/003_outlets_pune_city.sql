-- Outlets are Pune-only. Run in Supabase SQL Editor.

-- Add city column to outlets (default Pune)
alter table outlets
add column if not exists city text default 'Pune';

-- Set existing outlets to Pune
update outlets set city = 'Pune' where city is null;

comment on column outlets.city is 'City served (e.g. Pune). Bot validates address is in this city.';

-- Optional: Pune areas for future area-based outlet assignment
create table if not exists pune_areas (
  id uuid primary key default gen_random_uuid(),
  area_name text not null unique,
  outlet_id uuid references outlets(id),
  created_at timestamp default now()
);

comment on table pune_areas is 'Optional: map Pune areas to preferred outlet for smarter assignment.';

-- Example areas; link to outlets so address "Kothrud" books at that outlet
insert into pune_areas (area_name) values
  ('Kothrud'), ('Hinjewadi'), ('Viman Nagar'), ('FC Road'), ('Camp'),
  ('Aundh'), ('Baner'), ('Pimple Saudagar'), ('Wakad'), ('Hadapsar'),
  ('Kondhwa'), ('Shivajinagar'), ('Deccan'), ('Karve Road'), ('Sinhagad Road')
on conflict (area_name) do nothing;

-- Link Kothrud to first outlet (Laundry Central - A). Change outlet_id to match your real Kothrud outlet if you add one.
update pune_areas set outlet_id = (select id from outlets where is_active = true order by outlet_name limit 1) where area_name = 'Kothrud';
-- Optional: link more areas to outlets (e.g. Hinjewadi to second outlet, Viman Nagar to third)
update pune_areas set outlet_id = (select id from outlets where is_active = true order by outlet_name offset 1 limit 1) where area_name = 'Hinjewadi';
update pune_areas set outlet_id = (select id from outlets where is_active = true order by outlet_name offset 2 limit 1) where area_name = 'Viman Nagar';
