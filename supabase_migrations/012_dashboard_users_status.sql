-- Staff registration: new users are 'pending' until owner approves.
-- Run in Supabase SQL Editor (same project as admin dashboard).

alter table dashboard_users
  add column if not exists status text default 'approved' check (status in ('pending', 'approved', 'rejected'));

comment on column dashboard_users.status is 'pending = wait for approval; approved = can login; rejected = denied';

update dashboard_users set status = 'approved' where status is null;

create index if not exists dashboard_users_status_idx on dashboard_users(status);
