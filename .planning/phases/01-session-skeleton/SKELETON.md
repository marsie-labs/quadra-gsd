# Walking Skeleton — Quadra

**Phase:** 1
**Generated:** 2026-10-22

## Capability Proven End-to-End

A teammate creates a session from the home page and lands on its unguessable `/s/{session_id}` link, which renders the project name and the four quadrants from hosted Supabase. The single-worker server proves at startup that database change events reach it through Supabase Realtime.

The tracer that proves it is 01-02 (home form → SessionService → Repository → `create_session` RPC → read-back → canvas). Plans 01-03 to 01-06 expand from that slice.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Framework | FastAPI (≥0.159) hosting NiceGUI (≥3.18) via `ui.run_with(app, ...)`, called LAST in `create_app()` | User-specified, Python end to end. NiceGUI mounts at "/", so every FastAPI route and router (`/healthz`, Phase 5 `/api/...`) is registered before `run_with` (Pitfall 1) |
| UI model | Server-driven NiceGUI `@ui.page` functions registered by `app.ui.pages.register_pages()`; user text only via `ui.label` | No script mode (NiceGUI 3). Python is the single gateway, and the browser never holds Supabase keys |
| Data layer | Hosted Supabase Postgres 17 (ref `fligjsqzjoyedcuolwss`) through supabase-py 2.33 **async** client. `app.db.repository` is the only PostgREST importer | The async client is required for Realtime. One access path keeps rules testable |
| Schema & migrations | `supabase/migrations/*.sql` applied with `supabase db push --linked`. Tables `workspaces` (public token `session_id`), `quadrants`, `cards` (`order_index double precision`, `author` CHECK 1-40, `replica identity full`), `realtime_probe` | Version-controlled, append-only. Phase 4 adds the close/lock triggers without altering these columns |
| Invariants | Enforced in Postgres: atomic `create_session` RPC (workspace + 4 quadrants in one transaction), CHECKs mirroring app validation (token regex, project name 1-100, author 1-40) | The agent relies on DB-level integrity; UI validation is convenience |
| Access / auth | No accounts. The capability is `session_id = secrets.token_urlsafe(16)` (128 bits). RLS is on with no anon/authenticated policies; table privileges and RPC EXECUTE are revoked from anon/authenticated/public and granted to `service_role` only | Link-based access by design (PROJECT.md); the publishable key is proven denied |
| Participant identity | Display name in NiceGUI `app.storage.user` (signed cookie, `STORAGE_SECRET` ≥32 chars, 1-year `max_age`). Fixed per browser and read-only in the header. `ensure_display_name()` gates authoring | Locked decisions D-01 to D-04. No placeholder author ever exists |
| Realtime | One `RealtimeHub` owning one `AsyncRealtimeClient` and one channel (`quadra-db`) with Postgres Changes bindings added before a single `subscribe()`. The startup probe (nonce upsert → CDC event) runs in `strict` (default), `warn` or `off` mode and is reported at `/healthz` | No polling. The probe settles at first run whether `sb_secret_` works for Realtime; the legacy JWT fallback is `SUPABASE_REALTIME_KEY` |
| Configuration | `app.settings.Settings` (pydantic-settings, `SecretStr`, `.env`, git-ignored) | Typed, with masked secrets |
| Deployment target | Local only: `uv run python -m app` (uvicorn, **workers=1** hard-coded) against hosted Supabase | NiceGUI client state and the in-process hub need one process; production hosting is out of scope for v1 |
| Directory layout | `app/{settings,deps,models,tokens,main,__main__}.py`, `app/db/repository.py`, `app/services/sessions.py`, `app/realtime/hub.py`, `app/ui/{pages,home_page,canvas_page,identity}.py`; `tests/{unit,ui,integration}/`, `tests/ui/ui_main.py` harness, `tests/ui/fakes.py` | Matches 01-PATTERNS.md. One concern per module; the composition root is `app/main.py` |
| Testing | pytest 9 + pytest-asyncio (auto) + NiceGUI `user`/`create_user` fixtures (`--import-mode=importlib`). Integration tests are marked `integration` (excluded by default) and run against the hosted project | Headless UI tests in under a second; real-DB proofs on demand |
| Tooling | uv (lockfile), ruff (lint + format), Supabase CLI 2.121 | CLAUDE.md stack |

## Stack Touched in Phase 1

- [x] Project scaffold (framework, build, lint, test runner): 01-01
- [x] Routing, at least one real route: `/`, `/s/{session_id}` (01-02), `/healthz` (01-05)
- [x] Database, at least one real read AND one real write: `create_session` RPC write + embedded `workspaces → quadrants` read (01-02); probe upsert (01-04)
- [x] UI, at least one interactive element wired to the API: home "Create" form → SessionService → RPC → navigate (01-02); name banner and authoring gate (01-06)
- [x] Deployment, a documented local full-stack run command: `uv run python -m app` + README (01-05)

## Out of Scope (Deferred to Later Slices)

- Card add/edit/delete/move/reorder and their UI (Phases 2-3)
- Live card fan-out to browsers, the hub view registry, and resync on reconnect/resubscribe (Phase 2)
- Optimistic updates and echo reconciliation (Phase 3)
- `close_session` RPC, closed-lock and one-way-status triggers, read-only canvas (Phase 4)
- Agent results REST API `/api/sessions/{id}/results` (Phase 5)
- Copy-link button (UX-04), presence count (UX-02), connection indicator (UX-01), quadrant guidance (UX-03): v2
- Renaming a display name (excluded by D-03), accounts/auth, production hosting, multiple workers

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: participants add cards to any quadrant and see each other's cards appear live, relayed by the hub from Supabase Realtime (calls `ensure_display_name()` before each card write)
- Phase 3: edit, soft-delete, move and reorder cards with instant, duplicate-free feedback
- Phase 4: confirmed one-way close turns every client read-only, enforced by DB triggers
- Phase 5: the agent fetches the closed snapshot over REST (router registered before `ui.run_with`); full E2E demo
