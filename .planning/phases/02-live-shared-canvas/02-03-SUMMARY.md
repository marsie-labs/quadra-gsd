---
phase: 02-live-shared-canvas
plan: 03
subsystem: live-sync
tags: [nicegui, supabase-realtime, postgres-changes, pydantic, pytest, tdd]
status: complete

requires:
  - phase: 02-live-shared-canvas
    provides: "02-01 hub registry, _on_card, CanvasView.apply_card, card_event/seed_card fakes; 02-02 add-card edges"
provides:
  - "RealtimeHub._on_card handling INSERT, UPDATE (incl. cross-workspace moves) and DELETE; CardListener.remove_card; per-listener isolation via _fan_out"
  - "CanvasView.apply_card as a full-row projection (soft delete, quadrant move, stale updated_at guard) and CanvasView.remove_card"
  - "Offline projection tests (tests/ui/test_live_projection.py) and channel-wiring unit tests"
  - "Live SYNC-03 outside-writer proof and QUAL-02 convergence + latency proof against hosted Supabase"
  - "integration_settings skips only on missing variables (WR-08 closed)"
affects: [02-04-reconnect-recovery, 02-05-realtime-recovery, 03-edit-delete-move-ui]

actuals:
  tokens: 7000
  tasks: 2
  commits: 4

plan_head_before: 538e3a6f3128b8556688cee2f458510db5142092
plan_head_after: 13f9b7a60bf45406f25d1730e7750d53367a15a1
commits: 4

tech-stack:
  added: []
  patterns:
    - "Hub fan-out through one _fan_out(workspace_id, call) helper: iterates a list() copy and isolates each listener with its own try/except warning"
    - "Malformed-event path logs event type (known types only, else 'unknown') plus exception class; never record values"
    - "Latency measured event-driven: RecordingListener timestamps time.monotonic() in apply_card, test awaits asyncio.Queue with wait_for"

key-files:
  created:
    - tests/ui/test_live_projection.py
  modified:
    - app/realtime/hub.py
    - app/ui/canvas_view.py
    - tests/unit/test_hub_dispatch.py
    - tests/integration/test_live_cards.py
    - tests/conftest.py

key-decisions:
  - "DELETE needs only old_record.id: hosted Postgres Changes sends old_record = {id} on DELETE (RLS on) even with replica identity full, so a DELETE without workspace_id is broadcast as remove_card to every open canvas (unknown id is a no-op, removal can never disclose anything)"
  - "UPDATE old_record is complete on the hosted project (all 9 columns), so cross-workspace move detection by old_record.workspace_id works as planned"
  - "apply_card drops the old widget through remove_card before re-rendering, so the old quadrant's hint refreshes after state is updated (fixes a hint that stayed hidden after a move)"

patterns-established:
  - "Fake-hub tests feed hub._on_card(card_event(...)); channel-wiring tests feed _build_channel()._handle_message with callbacks[0].id=7 (probe) and callbacks[1].id=8 (cards)"

requirements-completed: [SYNC-01, SYNC-02, SYNC-03, QUAL-02, CARD-06]

coverage:
  - id: D1
    description: "Edits, quadrant moves, soft and hard deletes, and cross-session moves render live on every open canvas, in (order_index, created_at, id) order; identical cards stay separate"
    requirement: SYNC-02
    verification:
      - kind: unit
        ref: "tests/ui/test_live_projection.py (11 tests) and tests/unit/test_hub_dispatch.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Stale, malformed, unknown-type and foreign-session events change nothing; a failing canvas cannot block others; payload values are never logged"
    requirement: QUAL-02
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_dispatch.py#test_malformed_event_is_dropped_without_payload_in_logs"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_dispatch.py#test_failing_listener_does_not_block_others"
        status: pass
    human_judgment: false
  - id: D3
    description: "An outside writer's insert, text edit, soft delete and hard delete appear live in an open canvas on hosted Supabase"
    requirement: SYNC-03
    verification:
      - kind: integration
        ref: "tests/integration/test_live_cards.py#test_outside_writer_changes_appear_live"
        status: pass
    human_judgment: true
    rationale: "The literal Supabase SQL-editor run is the end-of-phase human check; automation uses a bypass PostgREST client as a stand-in"
  - id: D4
    description: "Two clients converge on identical, ordered cards with median at or under 1.0 s and no card over 2.0 s; another session receives nothing"
    requirement: SYNC-01
    verification:
      - kind: integration
        ref: "tests/integration/test_live_cards.py#test_two_clients_converge_with_latency"
        status: pass
    human_judgment: true
    rationale: "Latency is network dependent; one sample in one of two runs exceeded 1 s (see Latency)"
  - id: D5
    description: "A malformed .env (short STORAGE_SECRET) fails the integration run instead of skipping it"
    requirement: QUAL-02
    verification:
      - kind: command
        ref: "STORAGE_SECRET=short uv run pytest -m integration tests/integration/test_card_author_check.py"
        status: pass
    human_judgment: false
---

# Phase 2 Plan 03: Live Fidelity Summary

**The canvas is now a faithful live projection of the cards table (edits, moves, soft/hard deletes, cross-session moves), with stale/malformed events contained, and hosted-Supabase tests prove outside-writer sync and two-client convergence with measured latency.**

## Performance

- **Duration:** 5 min (2026-10-23T11:19:22Z to 11:24:39Z)
- **Tasks:** 2 (Task 1 TDD)
- **Files:** 1 created, 5 modified

## Accomplishments

- `_on_card` routes INSERT, UPDATE and DELETE; an UPDATE that changes `workspace_id` first removes the card from the old session's canvases. Every listener call is isolated, and iteration is over a list copy.
- `CanvasView.apply_card` projects the full row: soft delete removes, an older `updated_at` is ignored (equal applies), a changed quadrant moves the widget, and both quadrants' "No cards yet" hints refresh. `remove_card` added.
- Live proof (SYNC-03): insert, edit, soft delete and hard delete written by a client that bypasses Repository/SessionService show up in an open canvas.
- Live proof (QUAL-02/SYNC-01): two registered clients of one session see the same 5 cards in `list_cards` order; a client of another session receives none.
- WR-08: `integration_settings` skips only when every validation error is `missing`.

## TDD record

RED commit `442ba75` (`test(02-03)`), GREEN commit `abcccce` (`feat(02-03)`). Tests that were RED before Task 1's implementation (semantic assessment: each failed on the planned assertion, not on import/fixture errors):

- `tests/unit/test_hub_dispatch.py::test_delete_event_removes_by_old_record` (DELETE was ignored)
- `tests/unit/test_hub_dispatch.py::test_update_across_workspaces_removes_from_old_session` (old workspace never told)
- `tests/unit/test_hub_dispatch.py::test_malformed_event_is_dropped_without_payload_in_logs` (unknown event type "BOGUS" was applied instead of dropped)
- `tests/ui/test_live_projection.py::test_quadrant_change_moves_card` (old quadrant's hint stayed hidden)
- `tests/ui/test_live_projection.py::test_soft_delete_and_hard_delete_remove_card`
- `tests/ui/test_live_projection.py::test_deleting_the_last_card_brings_the_hint_back`
- `tests/ui/test_live_projection.py::test_stale_update_is_ignored` (stale text replaced the current one)
- `tests/ui/test_live_projection.py::test_update_across_sessions_leaves_old_canvas_and_fills_new`

Already green at RED (behavior from 02-01 retained, kept as regression guards): channel wiring, probe isolation, failing-listener isolation, register/unregister idempotence, identical cards, sort order, first event, event without canvas.

## Latency (SYNC-01, QUAL-02)

Hosted project, `time.monotonic()` from just before `add_card` to client B's `apply_card`. Two full runs of `test_two_clients_converge_with_latency`:

| Run | `latencies_ms=` | `over_1s_ms=` | Median |
|-----|-----------------|---------------|--------|
| Plan verify command (second command) | `latencies_ms=[830, 525, 525, 525, 533]` | `over_1s_ms=[]` | 525 ms |
| First full-file run | `latencies_ms=[926, 512, 1047, 543, 529]` | `over_1s_ms=[1047]` | 543 ms |

Verdicts against 1 s: in the verify run all 5 samples (830, 525, 525, 525, 533 ms) met 1 s. In the first run 4 samples met 1 s (926, 512, 543, 529 ms) and one did not.

**SYNC-01 deviation (explicit):** sample 3 of the first run, 1047 ms, exceeded 1 s by 47 ms. It is inside the planned gate (per-card ceiling 2.0 s, median ceiling 1.0 s), so the test passes, but it is recorded here as a miss of the "within ~1 s" target for a single card. The first card of each run is the slowest or near-slowest (830, 926 ms), consistent with Phase 1's measured 361/634/1266 ms probe round trips. No threshold was loosened.

## Task Commits

1. **Task 1 RED:** `442ba75` test(02-03): add failing tests for live edit, move and delete projection
2. **Task 1 GREEN:** `abcccce` feat(02-03): project edits, moves and deletes live on every open canvas
3. **Task 1 fix (deviation):** `7328799` fix(02-03): remove a hard-deleted card using only its id
4. **Task 2:** `13f9b7a` test(02-03): prove outside-writer sync and two-client convergence with latency on hosted Supabase

## Verification

- `uv run pytest tests/unit/test_hub_dispatch.py tests/ui/test_live_projection.py -q`: 33 passed.
- `uv run pytest -q`: 155 passed, 20 deselected; `uv run ruff check .` and `uv run ruff format --check .` clean.
- `uv run pytest -m integration tests/integration/test_live_cards.py -q -rs`: 3 passed, 0 skipped.
- `STORAGE_SECRET=short uv run pytest -m integration tests/integration/test_card_author_check.py -q -rs`: exits non-zero (2 errors, ValidationError), no skip.
- `grep -nE 'logger\.(error|exception)' app/realtime/hub.py`: only the pre-existing `run_startup_check` warn-mode line.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Hosted DELETE events carry only the primary key**
- **Found during:** Task 2 (`test_outside_writer_changes_appear_live`, hard-delete step; the hub logged `ignored cards event DELETE: KeyError`)
- **Issue:** The plan (and PITFALLS) assumed `replica identity full` gives a DELETE `old_record` with `workspace_id`. A measured probe against the hosted project showed `old_record` keys `['id']` only (documented Supabase behavior when RLS is enabled); INSERT and UPDATE records and the UPDATE `old_record` are complete.
- **Fix:** DELETE requires only `old_record.id`. With `workspace_id` present it routes to that workspace; without it, `remove_card(id)` goes to every registered workspace (no-op for unknown ids, removal only). The unit test that treated `{"id": "x"}` as malformed now treats an empty `old_record` as malformed, and `test_delete_with_only_the_primary_key_removes_from_every_canvas` plus a UI test cover the real shape.
- **Files modified:** app/realtime/hub.py, tests/unit/test_hub_dispatch.py, tests/ui/test_live_projection.py
- **Commit:** 7328799

**2. [Rule 1 - Bug] Old quadrant's "No cards yet" hint stayed hidden after a move**
- **Found during:** Task 1 RED run (`test_quadrant_change_moves_card`)
- **Issue:** 02-01's `apply_card` refreshed the old quadrant's hint before updating `_cards`, so the stale entry still counted.
- **Fix:** `apply_card` now drops the old card through `remove_card` (state first, then hint refresh) before re-rendering.
- **Commit:** abcccce

**Total deviations:** 2 auto-fixed (2 bugs). **Impact:** none on scope; the DELETE finding changes the Phase 3 assumption that DELETE events identify their session (they do not on this project).

## Known Stubs

None.

## Threat Flags

None. T-02-13/14/15/16/17 mitigations are implemented and tested as planned; no packages installed (pyproject.toml and uv.lock unchanged).

## Issues Encountered

None open. End-of-phase human check (SQL editor insert/update/soft-delete in two real browsers, per the plan) is still pending and belongs to phase verification.

## Self-Check: PASSED

- Files present: app/realtime/hub.py, app/ui/canvas_view.py, tests/ui/test_live_projection.py, tests/unit/test_hub_dispatch.py, tests/integration/test_live_cards.py, tests/conftest.py
- Commits present: 442ba75, abcccce, 7328799, 13f9b7a
