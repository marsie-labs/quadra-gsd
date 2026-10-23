# Quadra

## What This Is

Quadra is a realtime collaborative boundary canvas: a small team opens a shared session via link and fills four quadrants — **IS**, **IS NOT**, **DOES**, **DOES NOT** — with sticky-note cards, seeing each other's changes live. When the team finishes, anyone closes the session, locking the canvas read-only. An external Python agent harness then pulls the complete, structured result by `session_id` to summarize it or produce a report.

Built in Python end-to-end: FastAPI + NiceGUI for the server and UI, Supabase PostgreSQL for persistence, and supabase-py Realtime subscriptions relayed by the Python server to connected browsers.

## Core Value

Everyone on the link sees the same four-quadrant canvas update live, and once closed, the agent gets one complete, trustworthy snapshot of it — never a half-finished one.

## Requirements

### Validated

- ✓ User can create a new session by entering a project name; system generates a unique, unguessable `session_id` — Phase 1
- ✓ New session instantiates an active canvas linked to the four quadrants: IS, IS NOT, DOES, DOES NOT (created atomically) — Phase 1
- ✓ Session is accessible via shareable link only (no accounts/login); anyone with link can join; unknown link shows not-found — Phase 1
- ✓ On first visit, participant is prompted for a display name, remembered in their browser across reloads — Phase 1
- ✓ App runs locally with documented setup (env vars, migrations, single worker); startup check proves DB change events reach the Python server — Phase 1
- ✓ Participant's display name is used as card author (server-side, never from the request) — Phase 2
- ✓ Server holds a supabase-py Realtime subscription on the cards table and relays changes to every browser on that session, including direct DB edits — Phase 2
- ✓ Participant can add a text card to any quadrant (trimmed, 1-500 code points, enforced in UI, service and DB) — Phase 2
- ✓ Every card stores metadata: quadrant ID, order index, author, created/updated timestamps, deleted timestamp — Phase 2
- ✓ Card changes broadcast to all clients via Supabase Realtime events, no polling; canvases resync after browser reconnect or server restart — Phase 2
- ✓ Participant can edit a card's text inline (Enter saves, Shift+Enter newline, blur saves, Esc cancels); edits show live with "(edited)", trigger-stamped `text_updated_at` — Phase 3
- ✓ Participant can soft-delete a card (row kept with `deleted_at`, toast, no confirmation by decision) — Phase 3
- ✓ Participant can move a card to another quadrant via the card menu's "Move to" (lands at the end of the target) — Phase 3
- ✓ Participant can reorder cards within a quadrant (Move up/down; midpoint `order_index`, never renumbers) — Phase 3
- ✓ Own actions feel instant: optimistic overlay, in-place render (no duplicate/flicker on echo), rollback with a message on failure; an open draft survives others' changes — Phase 3

### Active

**Intent 3 — Explicit session closure and on-demand agent retrieval**
- [ ] Prominent "Finish / Close Session" button available to any participant, with confirmation
- [ ] Closing transitions workspace status `open` → `closed`; canvas becomes read-only for all connected clients immediately
- [ ] Closed is terminal — no reopen; continuing means starting a new session
- [ ] Writes to a closed session are rejected server-side (not just hidden in UI)
- [ ] REST endpoint (FastAPI) lets agent harness fetch results by `session_id`
- [ ] Fetch on open session returns explicit error (409 Conflict, message "Session is still open")
- [ ] Fetch on closed session returns complete structured JSON: session metadata + all live cards grouped by quadrant with metadata and timestamps; soft-deleted cards excluded
- [ ] Fetch on unknown `session_id` returns 404

**Quality**
- [ ] Automated tests cover realtime sync across clients, card operations, close/lock rules, and agent fetch responses (open/closed/unknown)
- [ ] End-to-end demo works: create session → 2+ browsers edit cards live → close → agent GETs full JSON

### Out of Scope

- User accounts / authentication / roles — link-based access is the deliberate model for fast team collaboration
- Facilitator/admin link separate from participant link — any participant can close; keeps model simple
- Reopening closed sessions — closed is final so the agent always reads a stable snapshot
- Drag-and-drop card movement — move menu chosen for reliability; can add later
- MCP (FastMCP) interface for agent — REST only for v1
- Soft-deleted cards in agent export — excluded; export reflects final canvas only
- Production deployment/hosting — local dev against hosted Supabase for now
- Large-scale sessions (30+ concurrent) — designed for 2–10 person teams
- Agent-side summarization logic — Quadra only serves data; the external harness does the summarizing

## Context

- **Domain:** "IS / IS NOT / DOES / DOES NOT" is a boundary-definition workshop technique for scoping a product, feature, or problem. Quadra digitizes it for small teams and hands the outcome to an AI agent for summarization/reporting.
- **Realtime model:** User chose Python as single gateway — supabase-py subscribes server-side to Postgres changes; FastAPI/NiceGUI pushes updates to browsers over NiceGUI's own WebSocket. Browsers never talk to Supabase directly. NiceGUI is server-driven UI, so "optimistic UI" means immediate server-side UI update for the acting client while Realtime fans out to others.
- **Consumer:** External Python agent harness, calling a REST endpoint with only `session_id`.
- **Scale:** 2–10 participants per session, few concurrent sessions.
- **Environment:** Local dev, hosted Supabase project already exists (keys available).
- **Origin:** Requirements came from three written intents (workspace init, realtime card management, closure + agent retrieval).

## Constraints

- **Tech stack**: Python, FastAPI, NiceGUI, Supabase PostgreSQL, supabase-py Realtime — user-specified
- **Realtime**: Must use Supabase Realtime events, no custom server-side polling loops — user requirement
- **Access**: Link-based, no auth — speed of collaboration over security
- **Data integrity**: Closed sessions must be immutable at server/DB level — agent relies on stable snapshot
- **Infra**: Hosted Supabase project (existing); app runs locally for v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI + NiceGUI | Python end-to-end; NiceGUI runs on FastAPI and is server-driven over WebSocket | ✓ Good — Phase 1 skeleton works; launcher hard-codes a single worker |
| Python relays Realtime to browsers (supabase-py server-side) | Python stays single gateway; browsers never hold Supabase keys | ✓ Good — one global subscription fanned out per workspace; live in ~1 s across browsers (UAT, Phase 2) |
| Sticky-note cards per quadrant | Matches workshop practice; supports add/edit/move/delete | ✓ Good — add (Phase 2); edit, delete, move, reorder (Phase 3), UAT 6/6 |
| Anyone with link can close session | No auth model; confirmation dialog guards accidents | — Pending |
| Display name on join (browser-remembered) | Author identifier without accounts | ✓ Good — inline banner, 1-year session cookie, never overwrites a stored name (Phase 1) |
| Closed is terminal, no reopen | Agent always sees stable final snapshot | — Pending |
| Agent API: REST only, 409 when open | Simple contract for harness; explicit error semantics | — Pending |
| Soft-delete; exclude deleted from export | Preserve history in DB, clean output for agent | ✓ Soft-delete shipped Phase 3 (no hard-delete path in the repository); export exclusion pending Phase 5 |
| Move via menu, not drag-and-drop | Reliability over polish for v1 | ✓ Good — card menu Edit / Move to / Move up / Move down / Delete; confirmed in UAT (Phase 3) |
| New `sb_secret_` key for Realtime; legacy JWT only as optional override | Legacy keys deprecated end of 2026; hosted Realtime accepts the new key | ✓ Verified Phase 1 (361–1266 ms round trip, override unset) |
| Workspace invariants (atomic create, name length) enforced in Postgres | Agent relies on DB-level integrity, not UI checks | ✓ Good — UI/service/DB name-length parity proven live (Phase 1) |
| Retry session creation once, only on unique-violation 23505 | Token collision is the only retryable failure; others must surface | ✓ Good (Phase 1) |
| Home create is single-shot (re-entrancy guard, locked until navigation) | Double Enter/click created duplicate sessions | ✓ Good — confirmed in UAT (Phase 1) |
| Card times shown as HH:MM in server local zone, full timestamp on hover | Simple for local v1; no timezone negotiation | ✓ Good (Phase 2); caveat for cross-timezone teams |
| Snapshot on page open and every reconnect, buffered events replayed through a stale `updated_at` guard | Missed Realtime events must never leave a stale canvas or undo newer changes | ✓ Good — offline/online and server-restart UAT passed (Phase 2) |
| Hub supervisor with single-flight recovery (1-30 s backoff); canvases resync only after the nonce probe re-proves change capture | Silent dead subscriptions would look live | ✓ Good (Phase 2); depends on realtime 2.33 private `_listen_task`, guarded by a test |
| Author name already in effect wins over a late dialog entry (multi-tab backstop) | One browser = one display name | ✓ Good — confirmed in UAT (Phase 2) |
| `cards_touch` trigger owns `updated_at` (strictly increasing) and `text_updated_at` | The stale guard and "(edited)" must not depend on any writer's clock | ✓ Good — forged/rewound stamps overridden on hosted DB (Phase 3) |
| Reorder by fractional midpoint, one row written; edges ±1024 | No renumbering write storms under concurrent reorders | ✓ Good (Phase 3); float gap can exhaust after ~50 alternating swaps (review WR-03, open) |
| Optimistic overlay with a single guarded `_write` path and per-card busy guard | Instant feel without duplicates; one place for rollback and CardGone | ✓ Good (Phase 3); failed save drops the draft (review WR-01, open) |
| Executor runs on the main tree when plans need hosted Supabase | Worktrees lack the gitignored `.env`, so hosted tests silently skip | ✓ Phase 3 ran sequentially; executor still cannot `supabase db push` — human pushes migrations |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-23 after Phase 3*
