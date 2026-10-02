alter table public.app_settings
add column if not exists destination_chat_id bigint;

alter table public.app_settings
add column if not exists important_destination_chat_id bigint;

update public.app_settings
set
    destination_chat_id = -1004372584244,
    important_destination_chat_id = -1004497281225
where id = 1;
