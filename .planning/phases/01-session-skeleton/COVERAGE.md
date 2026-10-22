# API Coverage — Supabase (supabase-py 2.33 async client, Realtime 2.33, Supabase CLI)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Scope: Phase 1 (Session Skeleton). Later phases re-decide each OPT-OUT row against the full surface instead of inheriting it silently.

| capability | decision | reason |
|---|---|---|
| client-acreate_client-async | INTEGRATE | |
| postgrest-select-embedded-maybe_single | INTEGRATE | |
| postgrest-rpc | INTEGRATE | |
| postgrest-upsert | INTEGRATE | |
| postgrest-insert | OPT-OUT | not needed yet; app card inserts arrive with CARD-01 in Phase 2 (Phase 1 inserts only inside the cards.author constraint test) |
| postgrest-update | OPT-OUT | not needed yet; card edit/move/soft-delete and session close land in Phases 3-4 |
| postgrest-delete | OPT-OUT | explicitly out of scope for the app; cards are soft-deleted via deleted_at (CARD-03), and tests use delete only for cleanup |
| realtime-postgres_changes | INTEGRATE | |
| realtime-broadcast | OPT-OUT | explicitly out of scope; Postgres Changes was chosen over Broadcast-from-Database at 2-10 users (CLAUDE.md Alternatives Considered) |
| realtime-presence | OPT-OUT | not needed yet; the presence count is UX-02 (v2) |
| auth-gotrue | OPT-OUT | explicitly out of scope; link-based access with no accounts (PROJECT.md Out of Scope) |
| storage-buckets | OPT-OUT | not needed; cards are text only |
| edge-functions-invoke | OPT-OUT | not needed; the Python server is the single gateway |
| cli-db-push-and-migration-list | INTEGRATE | |
| key-secret-server-side | INTEGRATE | |
| key-legacy-service_role-jwt-realtime-fallback | INTEGRATE | |
| key-publishable-browser | OPT-OUT | explicitly out of scope; browsers never talk to Supabase (used only by the anon-denial integration test) |
