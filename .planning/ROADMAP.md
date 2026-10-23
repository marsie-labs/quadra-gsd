# Roadmap: Quadra

## Overview

Quadra goes from an empty repo to a working, link-shared IS / IS NOT / DOES / DOES NOT canvas in five vertical slices. Phase 1 stands up the walking skeleton: a session can be created, opened by link, and joined with a display name, on top of the Supabase schema and a proven Realtime connection. Phase 2 adds the core value, which is cards that appear live for everyone. Phase 3 completes card editing with optimistic UI. Phase 4 adds the one-way close that freezes the canvas. Phase 5 opens the agent results API and verifies the whole flow end to end.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Session Skeleton** - Create a session, share its link, join with a display name, see the four empty quadrants (completed 2026-10-22)
- [ ] **Phase 2: Live Shared Canvas** - Participants add cards and see each other's cards appear live via Supabase Realtime
- [ ] **Phase 3: Card Editing** - Edit, delete, move and reorder cards with instant, duplicate-free feedback
- [ ] **Phase 4: Session Close & Lock** - Confirmed one-way close turns every client read-only, enforced in the DB
- [ ] **Phase 5: Agent Results & E2E** - Agent fetches the closed snapshot over REST; full flow verified end to end

## Phase Details

### Phase 1: Session Skeleton

**Goal**: A user can create a session, share its unguessable link, and teammates can open it, enter a display name, and see the four labeled quadrants. The schema, project setup and Realtime connection are proven underneath.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: SESS-01, SESS-02, SESS-03, SESS-04, SESS-05, IDEN-01, IDEN-02, QUAL-04
**Success Criteria** (what must be TRUE):
  1. User enters a project name on the home page and lands on `/s/<session_id>`, where `session_id` is a ≥128-bit random token
  2. Opening that link in a second browser, with no login, shows the same session with four labeled quadrants: IS, IS NOT, DOES, DOES NOT
  3. First-time visitor is prompted for a display name; after a reload they are not asked again and their name is shown
  4. Opening a link with an unknown `session_id` shows a not-found page
  5. Developer can follow the README to set env vars, apply migrations to the hosted Supabase project, and start the app (single worker); a startup check confirms DB change events reach the Python server

**Plans:** 7/7 plans complete

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Toolchain bootstrap: dependency legitimacy gate, uv project, pytest/ruff config, Settings, Supabase CLI config

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02-PLAN.md — Tracer: home-page Create lands on /s/{session_id} rendered from hosted Supabase (init migration pushed)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 01-03-PLAN.md — Session link hardening: project-name validation, malformed-link 404, token retry, atomic-create/RLS proofs
- [x] 01-04-PLAN.md — Realtime hub: nonce-matched startup round-trip probe against hosted Supabase (settles which Realtime key works)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 01-05-PLAN.md — Composition root + /healthz, 1-year session cookie, single-worker launcher, README

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 01-06-PLAN.md — Display-name identity: inline banner, per-browser memory, ensure_display_name() gate, author constraint, second no-login browser

**Wave 6** *(gap closure; blocked on Wave 5 completion)*
- [x] 01-07-PLAN.md — Double-submit guard: per-page re-entrancy flag on home-page create (double Enter / double click make one session), locked until navigation, released on failure (closes VERIFICATION gap / REVIEW WR-01)

**UI hint**: yes

### Phase 2: Live Shared Canvas

**Goal**: Participants add cards to any quadrant, and every connected browser on the session sees them appear live, relayed by the Python server from Supabase Realtime.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: IDEN-03, CARD-01, CARD-06, CARD-07, SYNC-01, SYNC-02, SYNC-03, SYNC-04, QUAL-02
**Success Criteria** (what must be TRUE):
  1. Participant can add a text card to any quadrant; empty text and text over 500 characters are rejected with a message
  2. A card added in browser A appears in browser B within ~1s without refresh, showing author name and time; it is stored with quadrant, order index, author and timestamps
  3. A card row inserted directly in the database (e.g. Supabase SQL editor) appears live in open browsers, which proves updates come from Realtime and not polling
  4. After a browser reconnect or a server restart, the canvas shows every card, including ones added while disconnected
  5. An automated integration test against Supabase shows two clients converging on the same cards via Realtime

**Plans:** 5/5 plans executed

Plans:
**Wave 1**
- [x] 02-01-PLAN.md — Tracer: a card added in browser A is stored in hosted Supabase and appears live in browser B via the Realtime hub; reopened canvas shows stored cards

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 02-02-PLAN.md — Authoring rules: [BLOCKING] author-nonblank migration push (WR-07), card text validation messages, name gate on add, double-submit guard, CARD-07 storage proofs

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 02-03-PLAN.md — Live fidelity: edits/moves/deletes and DB-direct changes projected live; two-client convergence and latency proof against hosted Supabase

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 02-04-PLAN.md — Browser reconnect and server restart recovery: buffered snapshot resync, 503 on DB failure (WR-05), live restart test

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 02-05-PLAN.md — Realtime connection recovery: re-join/error/silent-close handling with capped backoff, canvas resync after re-proof, README Phase 2 docs

**UI hint**: yes

### Phase 3: Card Editing

**Goal**: Participants can edit, delete, move and reorder cards collaboratively, and their own actions feel instant.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: CARD-02, CARD-03, CARD-04, CARD-05, CARD-08
**Success Criteria** (what must be TRUE):
  1. Participant can edit a card's text, and other participants see the new text live
  2. Participant can delete a card; it disappears for everyone while the row stays in the DB with a deleted timestamp
  3. Participant can move a card to another quadrant via a move menu; it leaves the old quadrant and appears in the new one for all clients
  4. Participant can reorder a card up/down within its quadrant; order matches across clients and after reload
  5. The acting participant sees their change instantly with no duplicate or flicker when the Realtime echo arrives; a failed write rolls back with a message

**Plans**: TBD
**UI hint**: yes

### Phase 4: Session Close & Lock

**Goal**: Any participant can finish the session with a confirmation. The canvas then becomes permanently read-only for everyone, and the database guarantees it.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: CLOS-01, CLOS-02, CLOS-03, CLOS-04, CLOS-05
**Success Criteria** (what must be TRUE):
  1. Every participant sees a prominent "Finish / Close Session" button; clicking it opens a confirmation dialog warning that closing cannot be undone, and cancelling leaves the session open
  2. After confirming, all connected clients switch to read-only and show a closed banner within ~1s
  3. Card writes to a closed session (stale tab, direct repository/DB call) are rejected by the database, and the user sees a clear "session closed" message
  4. Closing an already-closed session is a harmless no-op, and no path (UI or DB) can reopen it

**Plans**: TBD
**UI hint**: yes

### Phase 5: Agent Results & E2E

**Goal**: The external agent harness can fetch a closed session's complete, structured snapshot by `session_id`, and the whole flow is verified end to end.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: API-01, API-02, API-03, API-04, API-05, QUAL-01, QUAL-03
**Success Criteria** (what must be TRUE):
  1. `GET /api/sessions/{session_id}/results` returns 404 for an unknown session and 409 with "Session is still open" for an open one
  2. For a closed session it returns 200 JSON with session_id, project_name, status, created_at, closed_at, and four quadrants whose cards (id, text, author, created_at, updated_at) are ordered by order index, with soft-deleted cards excluded
  3. Automated test suite covering card operations, close/lock rules and all three agent responses passes
  4. Documented E2E demo works: create session → 2+ browsers edit live → close → agent GET returns the full JSON

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Session Skeleton | 7/7 | Complete    | 2026-10-22 |
| 2. Live Shared Canvas | 5/5 | In Progress | - |
| 3. Card Editing | 0/TBD | Not started | - |
| 4. Session Close & Lock | 0/TBD | Not started | - |
| 5. Agent Results & E2E | 0/TBD | Not started | - |
