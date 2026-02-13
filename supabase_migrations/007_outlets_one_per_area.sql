-- One outlet per Pune area. Run in Supabase SQL Editor.
-- Adds outlets for every area (Kothrud, FC Road, Kondhwa, etc.) and links pune_areas to them.

-- 1) Ensure all areas exist in pune_areas
insert into pune_areas (area_name) values
  ('Kothrud'), ('Hinjewadi'), ('Viman Nagar'), ('FC Road'), ('Camp'),
  ('Aundh'), ('Baner'), ('Pimple Saudagar'), ('Wakad'), ('Hadapsar'),
  ('Kondhwa'), ('Shivajinagar'), ('Deccan'), ('Karve Road'), ('Sinhagad Road'),
  ('Koregaon Park'), ('MG Road'), ('SB Road'), ('JM Road')
on conflict (area_name) do nothing;

-- 2) Create one outlet per area (skip if outlet already exists for that name)
-- location is required by outlets table; we set it to the area name (e.g. 'Kothrud', 'FC Road')
insert into outlets (outlet_name, is_active, city, location)
select 'LaundryOps - ' || pa.area_name, true, 'Pune', pa.area_name
from pune_areas pa
where not exists (
  select 1 from outlets o where o.outlet_name = 'LaundryOps - ' || pa.area_name
);

-- 3) Link each area to its outlet
update pune_areas pa
set outlet_id = (
  select o.id from outlets o where o.outlet_name = 'LaundryOps - ' || pa.area_name limit 1
)
where pa.outlet_id is null
   or pa.outlet_id <> (select o.id from outlets o where o.outlet_name = 'LaundryOps - ' || pa.area_name limit 1);

comment on column outlets.outlet_name is 'Display name e.g. LaundryOps - Kothrud (one per area)';
