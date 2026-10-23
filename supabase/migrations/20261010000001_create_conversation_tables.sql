-- Database-backed chat memory (so the chatbot's follow-up/context handling survives page
-- reloads and works the same from any device), added for: database-backed conversation
-- context. Lives in the same private rag schema as the chunk/document tables above -
-- no new database, and this migration only ADDs tables, it never touches the existing ones.
create table if not exists rag.conversations (
    session_id       text primary key,
    created_at       timestamptz not null default now(),
    last_active_at   timestamptz not null default now(),
    last_product_ids integer[] not null default array[]::integer[]
);

create table if not exists rag.messages (
    id          bigserial primary key,
    session_id  text not null references rag.conversations(session_id) on delete cascade,
    role        text not null check (role in ('user', 'assistant')),
    content     text not null,
    product_ids integer[] not null default array[]::integer[],
    sources     jsonb,
    created_at  timestamptz not null default now()
);
create index if not exists messages_session_created_idx
    on rag.messages (session_id, created_at);

alter table rag.conversations enable row level security;
alter table rag.messages enable row level security;

do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on rag.conversations from %I', r);
            execute format('revoke all on rag.messages from %I', r);
        end if;
    end loop;
end $$;
