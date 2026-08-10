create table if not exists public.channel_checkpoints (
    source_chat_id bigint primary key,
    source_channel text not null,
    last_message_id bigint not null check (last_message_id >= 0),
    updated_at timestamptz not null default now()
);

create or replace function public.set_channel_checkpoint_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists channel_checkpoints_updated_at on public.channel_checkpoints;
create trigger channel_checkpoints_updated_at
before update on public.channel_checkpoints
for each row execute function public.set_channel_checkpoint_updated_at();

alter table public.channel_checkpoints enable row level security;
grant select, insert, update on public.channel_checkpoints to service_role;
