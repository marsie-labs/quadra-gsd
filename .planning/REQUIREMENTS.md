# Requirements: Quadra

**Defined:** 2026-10-22
**Core Value:** Everyone on the link sees the same four-quadrant canvas update live, and once closed, the agent gets one complete, trustworthy snapshot of it — never a half-finished one.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Sessions

- [ ] **SESS-01**: User can create a session by entering a project name and lands on that session's unique link
- [ ] **SESS-02**: Session link contains an unguessable `session_id` (≥128-bit random token)
- [ ] **SESS-03**: New session starts open with four quadrants IS, IS NOT, DOES, DOES NOT (created atomically)
- [ ] **SESS-04**: Anyone with the link can open and edit the session without logging in
- [ ] **SESS-05**: Opening an unknown session link shows a not-found page

### Identity

- [ ] **IDEN-01**: On first visit, participant is prompted for a display name
- [ ] **IDEN-02**: Display name is remembered in the browser across reloads and sessions
- [ ] **IDEN-03**: Participant's display name is recorded as author on cards they create

### Cards

- [ ] **CARD-01**: Participant can add a text card to any quadrant (empty rejected, max 500 chars)
- [ ] **CARD-02**: Participant can edit a card's text
- [ ] **CARD-03**: Participant can delete a card (soft-delete: gone for everyone, kept in DB)
- [ ] **CARD-04**: Participant can move a card to another quadrant via a move menu
- [ ] **CARD-05**: Participant can reorder a card within its quadrant via up/down controls
- [ ] **CARD-06**: Each card shows its author's name and time
- [ ] **CARD-07**: Each card stores quadrant, order index, author, created/updated timestamps, deleted timestamp
- [ ] **CARD-08**: Participant's own actions appear instantly with no duplicates when confirmation arrives; failed writes roll back with a message

### Sync

- [ ] **SYNC-01**: A card change by one participant appears for all others on the session within ~1s
- [ ] **SYNC-02**: Updates are delivered via Supabase Realtime events relayed by the Python server (no polling)
- [ ] **SYNC-03**: Changes made directly in the database (outside the app) also appear live
- [ ] **SYNC-04**: After a browser reconnect or server restart, the client shows current state

### Close

- [ ] **CLOS-01**: Any participant sees a prominent "Finish / Close Session" button
- [ ] **CLOS-02**: Closing requires confirming a dialog that warns it cannot be undone
- [ ] **CLOS-03**: After close, all connected clients switch to read-only immediately and show a closed banner
- [ ] **CLOS-04**: Card writes to a closed session are rejected at DB level; user sees a clear message
- [ ] **CLOS-05**: Closed is terminal: closing twice is a harmless no-op, and reopening is impossible

### Agent API

- [ ] **API-01**: Agent can call `GET /api/sessions/{session_id}/results`
- [ ] **API-02**: Unknown `session_id` returns 404
- [ ] **API-03**: Open session returns 409 with message "Session is still open"
- [ ] **API-04**: Closed session returns 200 JSON: session_id, project_name, status, created_at, closed_at, and four quadrants each with cards (id, text, author, created_at, updated_at) ordered by order index
- [ ] **API-05**: Soft-deleted cards are excluded from results

### Quality

- [ ] **QUAL-01**: Automated tests cover card operations, close/lock rules, and all agent responses
- [ ] **QUAL-02**: Integration tests against real Supabase verify realtime propagation between two clients
- [ ] **QUAL-03**: Documented E2E demo: create → 2+ browsers edit live → close → agent GET returns full JSON
- [ ] **QUAL-04**: App runs locally with documented setup (env vars, migrations, single worker)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Canvas UX

- **UX-01**: Connection indicator shows reconnecting state
- **UX-02**: Presence count shows how many people are in the session
- **UX-03**: Each quadrant shows short guidance text
- **UX-04**: One-click copy-link button

### Export

- **EXP-01**: Export includes `schema_version`
- **EXP-02**: Export includes `closed_by` (display name of closer)
- **EXP-03**: Export includes per-quadrant card counts
- **EXP-04**: Human-readable Markdown export
- **EXP-05**: FastMCP tool wrapping the results service

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| User accounts / authentication / roles | Link-based access is the deliberate model for fast team collaboration |
| Separate facilitator/admin link | Any participant can close; keeps model simple |
| Reopening closed sessions | Agent must always read a stable final snapshot |
| Drag-and-drop card movement | Move menu chosen for reliability in server-driven UI |
| MCP interface in v1 | REST only for v1 (FastMCP wrapper deferred to v2) |
| Soft-deleted cards in export | Export reflects final canvas only |
| Production deployment / hosting | Local dev against hosted Supabase for v1 |
| Sessions with 30+ concurrent users | Designed for 2–10 person teams |
| Agent-side summarization | Quadra serves data; external harness summarizes |
| Realtime co-editing inside a card (CRDT) | Last-write-wins is fine for one-line cards |
| Voting, timers, grouping, comments | Retro-tool feature creep; not in intents |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SESS-01 | Phase 1 | Gaps Found |
| SESS-02 | Phase 1 | Gaps Found |
| SESS-03 | Phase 1 | Gaps Found |
| SESS-04 | Phase 1 | Gaps Found |
| SESS-05 | Phase 1 | Gaps Found |
| IDEN-01 | Phase 1 | Gaps Found |
| IDEN-02 | Phase 1 | Gaps Found |
| IDEN-03 | Phase 2 | Pending |
| QUAL-04 | Phase 1 | Gaps Found |
| CARD-01 | Phase 2 | Pending |
| CARD-06 | Phase 2 | Pending |
| CARD-07 | Phase 2 | Pending |
| SYNC-01 | Phase 2 | Pending |
| SYNC-02 | Phase 2 | Pending |
| SYNC-03 | Phase 2 | Pending |
| SYNC-04 | Phase 2 | Pending |
| QUAL-02 | Phase 2 | Pending |
| CARD-02 | Phase 3 | Pending |
| CARD-03 | Phase 3 | Pending |
| CARD-04 | Phase 3 | Pending |
| CARD-05 | Phase 3 | Pending |
| CARD-08 | Phase 3 | Pending |
| CLOS-01 | Phase 4 | Pending |
| CLOS-02 | Phase 4 | Pending |
| CLOS-03 | Phase 4 | Pending |
| CLOS-04 | Phase 4 | Pending |
| CLOS-05 | Phase 4 | Pending |
| API-01 | Phase 5 | Pending |
| API-02 | Phase 5 | Pending |
| API-03 | Phase 5 | Pending |
| API-04 | Phase 5 | Pending |
| API-05 | Phase 5 | Pending |
| QUAL-01 | Phase 5 | Pending |
| QUAL-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-22*
*Last updated: 2026-10-22 after Phase 1 plan-check (IDEN-03 remapped from Phase 1 to Phase 2 by user decision)*
