alter table public.cards add constraint cards_author_nonblank check (char_length(btrim(author)) between 1 and 40);
alter table public.workspaces add constraint workspaces_closed_by_nonblank check (closed_by is null or char_length(btrim(closed_by)) between 1 and 40);
notify pgrst, 'reload schema';
