# API Coverage — Supabase (supabase-py 2.33 async client, Realtime 2.33, Supabase CLI)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Scope: Phase 2 (Live Shared Canvas). Every Phase 1 row was re-decided against this phase's surface (cards written by the app, card changes relayed live, reconnect recovery); nothing is inherited silently. Rows new in Phase 2 are marked (new).

| capability | decision | reason |
|---|---|---|
| client-acreate_client-async | INTEGRATE | |
| postgrest-select-embedded-maybe_single | INTEGRATE | |
| postgrest-select-filter-order-limit | INTEGRATE | |
| postgrest-rpc | INTEGRATE | |
| postgrest-upsert | INTEGRATE | |
| postgrest-insert | INTEGRATE | |
| postgrest-update | OPT-OUT | not needed yet; app card edits/moves/soft-deletes are Phase 3, close is Phase 4. Phase 2 updates rows only in tests, as an outside writer (SYNC-03) |
| postgrest-delete | OPT-OUT | explicitly out of scope for the app; cards are soft-deleted via deleted_at (CARD-03, Phase 3). Tests hard-delete only for cleanup and to prove DELETE events are projected |
| realtime-postgres_changes | INTEGRATE | |
| realtime-postgres_changes-server-filter | OPT-OUT | not needed; one global channel routed in-process by workspace_id suits 2-10 users (CLAUDE.md Alternatives); per-session filters add channel lifecycle (new) |
| realtime-subscribe-state-rejoin | INTEGRATE | |
| realtime-client-reconnect-rebuild | INTEGRATE | |
| realtime-broadcast | OPT-OUT | explicitly out of scope; Postgres Changes was chosen over Broadcast-from-Database at 2-10 users (CLAUDE.md Alternatives Considered) |
| realtime-presence | OPT-OUT | not needed yet; the presence count is UX-02 (v2) |
| realtime-set_auth-token-refresh | OPT-OUT | not needed; the server connects with the long-lived sb_secret_ key, not a user JWT that expires. The 24 h connection cap is covered by realtime-client-reconnect-rebuild (new) |
| auth-gotrue | OPT-OUT | explicitly out of scope; link-based access with no accounts (PROJECT.md Out of Scope) |
| storage-buckets | OPT-OUT | not needed; cards are text only |
| edge-functions-invoke | OPT-OUT | not needed; the Python server is the single gateway |
| cli-db-push-and-migration-list | INTEGRATE | |
| key-secret-server-side | INTEGRATE | |
| key-legacy-service_role-jwt-realtime-fallback | INTEGRATE | |
| key-publishable-browser | OPT-OUT | explicitly out of scope; browsers never talk to Supabase (used only by the Phase 1 anon-denial integration test) |
