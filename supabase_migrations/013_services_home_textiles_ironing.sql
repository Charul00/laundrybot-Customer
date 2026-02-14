-- Add home textiles and ironing services. Run in Supabase SQL Editor.
-- Assumes services table has (id, service_name, base_price) or similar.

insert into services (service_name, base_price)
select 'home_textiles', 80
where not exists (select 1 from services where service_name = 'home_textiles' limit 1);

insert into services (service_name, base_price)
select 'premium_iron', 45
where not exists (select 1 from services where service_name = 'premium_iron' limit 1);

insert into services (service_name, base_price)
select 'press_iron', 35
where not exists (select 1 from services where service_name = 'press_iron' limit 1);

insert into services (service_name, base_price)
select 'steam_iron', 40
where not exists (select 1 from services where service_name = 'steam_iron' limit 1);

comment on table services is 'Laundry services: wash, iron, dry_clean, shoe_clean, home_textiles, premium_iron, press_iron, steam_iron';
