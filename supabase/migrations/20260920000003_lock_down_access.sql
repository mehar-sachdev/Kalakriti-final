-- Defence in depth.  The backend connects with the database owner role (which bypasses
-- RLS); every other role, including Supabase's anon and authenticated, gets nothing.
alter table rag.data_kalakriti_chunks enable row level security;
alter table rag.documents enable row level security;

do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on schema rag from %I', r);
            execute format('revoke all on all tables in schema rag from %I', r);
            execute format('revoke all on all sequences in schema rag from %I', r);
        end if;
    end loop;
end $$;
