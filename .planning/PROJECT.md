# Quadra

## What This Is

Quadra is a realtime collaborative boundary canvas: a small team opens a shared session via link and fills four quadrants — **IS**, **IS NOT**, **DOES**, **DOES NOT** — with sticky-note cards, seeing each other's changes live. When the team finishes, anyone closes the session, locking the canvas read-only. An external Python agent harness then pulls the complete, structured result by `session_id` to summarize it or produce a report.

Built in Python end-to-end: FastAPI + NiceGUI for the server and UI, Supabase PostgreSQL for persistence, and supabase-py Realtime subscriptions relayed by the Python server to connected browsers.

## Core Value

Everyone on the link sees the same four-quadrant canvas update live, and once closed, the agent gets one complete, trustworthy snapshot of it — never a half-finished one.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Intent 1 — Workspace and realtime canvas initialization**
- [ ] User can create a new session by entering a project name; system generates a unique `session_id`
- [ ] New session instantiates an active canvas linked to the four quadrants: IS, IS NOT, DOES, DOES NOT
- [ ] Session is accessible via shareable link only (no accounts/login); anyone with link can join and edit
- [ ] On first visit, participant is prompted for a display name, remembered in their browser, used as card author
- [ ] Server holds supabase-py Realtime subscriptions on workspace/card tables and relays changes to all connected browsers on that session (session init and modification)

**Intent 2 — Realtime collaborative boundary management**
- [ ] Participant can add a text card to any quadrant
- [ ] Participant can edit a card's text
- [ ] Participant can soft-delete a card
- [ ] Participant can move a card to another quadrant via a move menu/buttons (no drag-and-drop in v1)
- [ ] Participant can reorder cards within a quadrant (order index preserved)
- [ ] Every card stores metadata: quadrant ID, order index, author (display name), created/updated timestamps, deleted flag/timestamp
- [ ] Card mutations broadcast to all clients on the session via Supabase Realtime events — no custom polling loops
- [ ] UI feels smooth under light latency: optimistic local update or quick confirmation in NiceGUI

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
| FastAPI + NiceGUI | Python end-to-end; NiceGUI runs on FastAPI and is server-driven over WebSocket | — Pending |
| Python relays Realtime to browsers (supabase-py server-side) | Python stays single gateway; browsers never hold Supabase keys | — Pending |
| Sticky-note cards per quadrant | Matches workshop practice; supports add/edit/move/delete | — Pending |
| Anyone with link can close session | No auth model; confirmation dialog guards accidents | — Pending |
| Display name on join (browser-remembered) | Author identifier without accounts | — Pending |
| Closed is terminal, no reopen | Agent always sees stable final snapshot | — Pending |
| Agent API: REST only, 409 when open | Simple contract for harness; explicit error semantics | — Pending |
| Soft-delete; exclude deleted from export | Preserve history in DB, clean output for agent | — Pending |
| Move via menu, not drag-and-drop | Reliability over polish for v1 | — Pending |

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
*Last updated: 2026-10-22 after initialization*
