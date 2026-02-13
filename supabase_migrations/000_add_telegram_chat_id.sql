-- Run this in Supabase SQL Editor once. Links Telegram users to customers.

alter table customers
add column if not exists telegram_chat_id text unique;

comment on column customers.telegram_chat_id is 'Telegram chat_id for bot conversations';
