create type public.workspace_status as enum ('open', 'closed');
create type public.quadrant_kind as enum ('IS', 'IS_NOT', 'DOES', 'DOES_NOT');

create table public.workspaces (
  id           uuid primary key default gen_random_uuid(),
  session_id   text not null unique
               check (session_id ~ '^[A-Za-z0-9_-]{22,64}$'),
  project_name text not null
               check (char_length(project_name) between 1 and 100),
  status       public.workspace_status not null default 'open',
  created_at   timestamptz not null default now(),
  closed_at    timestamptz,
  closed_by    text check (closed_by is null or char_length(closed_by) between 1 and 40),
  constraint workspaces_closed_consistent
    check ((status = 'closed') = (closed_at is not null))
);

create table public.quadrants (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  kind         public.quadrant_kind not null,
  position     smallint not null check (position between 1 and 4),
  unique (workspace_id, kind),
  unique (workspace_id, position),
  unique (id, workspace_id)
);

create table public.cards (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.workspaces (id) on delete cascade,
  quadrant_id   uuid not null,
  text          text not null check (char_length(btrim(text)) between 1 and 500),
  order_index   double precision not null,
  author        text not null check (char_length(author) between 1 and 40),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  deleted_at    timestamptz,
  foreign key (quadrant_id, workspace_id)
    references public.quadrants (id, workspace_id)   -- card can only sit in a quadrant of its own session
);
create index cards_workspace_id_idx on public.cards (workspace_id);
create index cards_quadrant_order_idx
  on public.cards (quadrant_id, order_index, created_at, id) where deleted_at is null;

create table public.realtime_probe (
  id        smallint primary key default 1 check (id = 1),
  nonce     text not null,
  pinged_at timestamptz not null default now()
);

alter table public.workspaces     enable row level security;
alter table public.quadrants      enable row level security;
alter table public.cards          enable row level security;
alter table public.realtime_probe enable row level security;

revoke all on table public.workspaces, public.quadrants, public.cards, public.realtime_probe
  from anon, authenticated;
grant select, insert, update, delete
  on table public.workspaces, public.quadrants, public.cards, public.realtime_probe
  to service_role;

create function public.create_session(p_project_name text, p_session_id text)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_workspace_id uuid;
begin
  insert into public.workspaces (session_id, project_name)
  values (p_session_id, btrim(p_project_name))
  returning id into v_workspace_id;

  insert into public.quadrants (workspace_id, kind, position)
  select v_workspace_id, q.kind, q.position
  from (values
    ('IS'::public.quadrant_kind, 1),
    ('IS_NOT', 2),
    ('DOES', 3),
    ('DOES_NOT', 4)
  ) as q (kind, position);

  return p_session_id;
end;
$$;

revoke execute on function public.create_session(text, text) from public, anon, authenticated;
grant  execute on function public.create_session(text, text) to service_role;

alter table public.cards replica identity full;   -- Phase 3 needs old quadrant on moves

do $$
declare t text;
begin
  foreach t in array array['workspaces', 'cards', 'realtime_probe'] loop
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;

notify pgrst, 'reload schema';
