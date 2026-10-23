alter table public.cards add column text_updated_at timestamptz;

create function public.cards_touch()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at := greatest(pg_catalog.clock_timestamp(), old.updated_at + interval '1 microsecond');
  if new.text is distinct from old.text then
    new.text_updated_at := new.updated_at;
  else
    new.text_updated_at := old.text_updated_at;
  end if;
  return new;
end;
$$;

create trigger cards_touch
  before update on public.cards
  for each row execute function public.cards_touch();

notify pgrst, 'reload schema';
