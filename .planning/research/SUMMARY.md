# Project Research Summary

**Project:** Quadra
**Domain:** Realtime collaborative workshop canvas (IS / IS NOT / DOES / DOES NOT) with agent-facing export
**Researched:** 2026-10-22
**Confidence:** HIGH (stack, architecture), MEDIUM (Realtime auth with new key format, reconnect behaviour)

## Executive Summary

Quadra is a narrow, link-shared collaborative board: four fixed quadrants of sticky-note cards, live for 2–10 people, ending in a one-way close that freezes a snapshot for an AI agent to fetch over REST. Comparable tools (EasyRetro, Metro Retro, Miro) use client-side SPAs talking to realtime backends; Quadra deliberately uses a server-driven Python UI (NiceGUI on FastAPI) with the Python process as the single gateway, subscribing to Supabase Realtime and relaying changes to browsers.

Recommended approach: single uvicorn process hosting FastAPI + NiceGUI; one async supabase-py client; one Realtime channel listening to `cards` and `workspaces` changes, feeding an in-process **RealtimeHub** that routes events to the NiceGUI views of the affected session. Postgres is the source of truth and enforces the invariants the agent relies on (closed sessions immutable, close is one-way, atomic session creation) through triggers and RPC functions. UI and REST share one service layer.

Key risks: (1) Realtime plumbing — async-only client, publication setup, and whether the new `sb_secret_` key works for Realtime — de-risk with a Phase 1 smoke test; (2) missed events after reconnect — resync full state from DB on every (re)connect; (3) optimistic UI echo duplicates — stable card ids + `updated_at` reconciliation; (4) lock only in UI — enforce in DB.

## Key Findings

### Recommended Stack

Python 3.12, FastAPI 0.159, NiceGUI 3.18 (mounted via `ui.run_with(app, storage_secret=...)`), supabase-py 2.33 async client (`acreate_client`) with bundled realtime 2.33, pydantic 2.14 + pydantic-settings 2.16, uvicorn 0.54 single worker. Tooling: uv, Supabase CLI migrations, ruff, pytest 9.1 + pytest-asyncio 1.4 + NiceGUI `user` fixture.

**Core technologies:**
- NiceGUI: server-driven UI over socket.io — makes "Python relays to browser" native
- supabase-py async + Realtime `on_postgres_changes`: DB-driven fan-out, no polling
- Postgres triggers/RPCs: invariants (lock, one-way close, atomic create) the agent can trust

### Expected Features

**Must have (table stakes):**
- Create session → unguessable link; display name on join
- Four labeled quadrants; add / edit / soft-delete / move (menu) / reorder (up/down) cards
- Live sync < ~1s with reconnect resync
- Confirmed close → read-only for everyone, DB-enforced
- `GET /api/sessions/{id}/results` → 404 / 409 "Session is still open" / 200 JSON (live cards grouped by quadrant)

**Should have (competitive):**
- Typed, versioned agent export (core differentiator)
- Presence count, card counts per quadrant (v1.x)

**Defer (v2+):**
- Drag-and-drop, voting/timers, MCP wrapper, duplicate-as-new, deployment/scaling

### Architecture Approach

Single Python process. NiceGUI pages (`/`, `/s/{session_id}`) and FastAPI router (`/api/sessions/{id}/results`) both call `SessionService` → `Repository` (supabase-py). `RealtimeHub` starts on app startup, subscribes once, keeps `session_id → views` registry, dispatches changes into each client's context, resyncs on reconnect.

**Major components:**
1. Schema + migrations — tables (workspaces, quadrants, cards), triggers, RPCs, publication, RLS
2. Repository + SessionService — all data access and rules, shared by UI and REST
3. RealtimeHub — subscription, registry, dispatch, resync
4. NiceGUI pages — create page, canvas page with optimistic updates and echo reconciliation
5. Results API — agent contract

### Critical Pitfalls

1. **Realtime silent failure** (sync client, missing publication, key/role) — Phase 1 smoke test: SQL write → Python callback
2. **Missed events after reconnect** — reload from DB on every (re)connect / resubscribe
3. **Optimistic echo duplicates** — stable UUIDs + `updated_at` comparison
4. **Lock only in UI / close races** — DB trigger + `UPDATE ... WHERE status='open'`
5. **Guessable session ids** — ≥128-bit random token; RLS deny-all for anon

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation & Data Layer
**Rationale:** Everything depends on schema and a proven Realtime connection; riskiest unknowns (key format, publication) surface here.
**Delivers:** uv project, settings, FastAPI+NiceGUI skeleton (single worker), Supabase migrations (tables, enums, indexes, RLS, publication, triggers, `create_session`/`close_session` RPCs), repository, Realtime smoke test.
**Addresses:** schema for all intents
**Avoids:** Pitfalls 1, 2, 7, 9

### Phase 2: Session Creation & Canvas Shell
**Rationale:** First user-visible slice; establishes page structure and identity.
**Delivers:** create page → `/s/{session_id}`; canvas showing four quadrants and existing cards; display name prompt persisted in `app.storage.user`; not-found page.
**Uses:** NiceGUI pages, SessionService

### Phase 3: Realtime Hub & Live Sync
**Rationale:** Core value; card ops should be built on top so every op is multi-client from day one.
**Delivers:** RealtimeHub (subscribe, registry, dispatch, disconnect cleanup, resubscribe + resync), canvas views react to DB changes made elsewhere.
**Implements:** Patterns 1 & 4
**Avoids:** Pitfalls 3, 4

### Phase 4: Card Operations
**Rationale:** Builds on hub; includes optimistic UI.
**Delivers:** add, edit, soft-delete, move via menu, reorder via up/down; metadata (author, timestamps, order index); echo reconciliation; validation (length, empty).
**Avoids:** Pitfalls 5, 8

### Phase 5: Session Close & Lock
**Rationale:** Needs live views to propagate lock.
**Delivers:** Finish button + confirm, `close_session` RPC, live read-only switch with banner, server/DB rejection of writes, friendly errors.
**Avoids:** Pitfall 6

### Phase 6: Agent Results API
**Rationale:** Depends on close semantics; small, well-defined.
**Delivers:** `GET /api/sessions/{session_id}/results` with 404/409/200, Pydantic response model with `schema_version`, ordered live cards per quadrant, session metadata.

### Phase 7: End-to-End Verification & Hardening
**Rationale:** "Done" bar is E2E + tests; consolidates multi-client realtime integration tests and the demo script.
**Delivers:** integration suite against Supabase (two views converge, write-after-close rejected, export correctness), README run/test instructions, E2E demo walkthrough.
**Avoids:** Pitfall 10

### Phase Ordering Rationale

- Data + Realtime proof first because every other phase depends on them and they hold the biggest unknowns.
- Hub before card ops so operations are designed for multi-client fan-out and echo reconciliation from the start.
- Close before API because the API's behaviour is defined by close semantics.
- Tests accompany every phase; Phase 7 adds cross-cutting E2E only.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Realtime auth with `sb_secret_` vs legacy `service_role` JWT; exact `on_postgres_changes` payload shape in realtime 2.33; Supabase CLI linking to existing hosted project
- **Phase 3:** realtime-py reconnect/resubscribe behaviour; NiceGUI client lifecycle hooks in 3.18 (`client.on_disconnect`, `client.connected()`)
- **Phase 4:** NiceGUI patterns for partial re-render without losing input focus

Phases with standard patterns (skip research-phase):
- **Phase 5, 6:** well-understood SQL/REST patterns

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions verified on PyPI 2026-10-22; user-specified core |
| Features | MEDIUM-HIGH | Narrow domain, decisions already made in questioning |
| Architecture | HIGH | Standard server-driven pattern; DB-enforced invariants |
| Pitfalls | MEDIUM-HIGH | Supabase caveats documented; realtime-py reconnect unverified |

**Overall confidence:** HIGH

### Gaps to Address

- Realtime + new secret key compatibility: verify in Phase 1 smoke test; fall back to legacy service_role JWT
- Exact Python payload shape for postgres_changes events: capture real payload in Phase 1, encode in a typed parser
- Integration test isolation on shared hosted project: unique data + cleanup; switch to local `supabase start` if flaky
- Supabase CLI access to hosted project (link/password) — user may need to run `supabase login` / `supabase link` interactively

## Sources

### Primary (HIGH confidence)
- PyPI JSON API — versions and dependency pins (2026-10-22)
- https://supabase.com/docs/reference/python/realtime-api — async-only Realtime
- realtime-py README — channel API, filters, subscribe states, JWT key
- https://supabase.com/docs/guides/realtime/postgres-changes — caveats and limits
- https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys.md — key formats
- https://nicegui.io/documentation (run, configuration/deployment, storage, testing)

### Secondary (MEDIUM confidence)
- https://supabase.com/blog/realtime-broadcast-from-database — scaling alternative
- https://newreleases.io/project/pypi/nicegui/release/3.0.0 — 3.0 breaking changes
- Collaborative board product conventions (Miro, FigJam, EasyRetro, Metro Retro)

### Tertiary (LOW confidence)
- Community claims about Postgres Changes scaling — not needed at v1 scale

---
*Research completed: 2026-10-22*
*Ready for roadmap: yes*
