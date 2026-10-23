---
phase: 03-card-editing
plan: 04
subsystem: ui
tags: [nicegui, soft-delete, move-card, optimistic-ui, realtime, composite-fk, supabase, pytest]

requires:
  - phase: 03-card-editing
    provides: "03-01 projection model (optimistic overlay, in-place _render, guarded _write, _update_live_card), 03-02 trigger-mirroring fake and CardGone, 03-03 card menu builder with Edit"
provides:
  - "Repository.soft_delete_card and move_card, both scoped by id, workspace_id and deleted_at is null; the repository has no hard-delete call"
  - "SessionService.delete_card (returns the deleted row or None, idempotent) and SessionService.move_card (end of target quadrant, CardGone when missing)"
  - "Card menu in D-07 order Edit, Move to (submenu of the three other quadrants), Delete; markers card-action-move, card-action-move-{KIND}, card-action-delete"
  - "Instant optimistic delete with toast 'Card deleted' and instant optimistic move, both rolling back with a message on failure"
  - "FakeRepository.soft_delete_card and move_card mirroring the scoped update, the gate and fail codes, and the composite-FK 23503"
affects: [03-05, phase-04-close-session, phase-05-agent-snapshot]

actuals:
  tokens: 10600
  tasks: 3
  commits: 5

plan_head_before: ebc9acc965092e1a25c3966fcaf29eb70a04552e
plan_head_after: bffbc6d39e71a933bba88d699a88b4fd88e71b1d

tech-stack:
  added: []
  patterns:
    - "A write that returns None means the card is already gone: _write removes it quietly, so idempotent deletes need no special UI path"
    - "Move to is a nested ui.menu inside an auto_close=False menu item; a chosen quadrant closes the top menu itself because a menu item closes only its nearest menu"
    - "The current quadrant's Move to item is hidden by _render (set_visibility), not removed, so a moved card needs no menu rebuild"
    - "The fake mirrors the real UPDATE order: no live match gives None before any constraint is checked, otherwise the composite FK raises 23503"

key-files:
  created:
    - tests/ui/test_card_actions.py
    - tests/integration/test_card_actions_live.py
  modified:
    - app/db/repository.py
    - app/services/sessions.py
    - app/ui/canvas_view.py
    - tests/ui/fakes.py

key-decisions:
  - "delete_card returns the deleted row or None; None (already deleted, or another session) is treated as success so a double click or two simultaneous deleters never see an error"
  - "The 'Card deleted' toast is shown together with the optimistic removal, before the write returns (D-08); a failed write then adds the failure message and restores the card"
  - "Move to is a submenu so the top-level menu keeps the D-07 shape; the item for the card's current quadrant is hidden rather than removed"
  - "No tombstone for deleted cards: the delete confirmation, the delete echo and the stale guard together keep a deleted card from reappearing; a late stale echo of an older edit is the pre-existing last-write-wins case and was not widened here"

patterns-established:
  - "_write(..., call returning CardView | None): None removes the card; a CardView goes through _apply (a deleted row removes it, a moved row repositions it)"
  - "Test double click as two synchronous clicks before any await, so both land before either handler task has run"

requirements-completed: [CARD-03, CARD-04, CARD-08]

coverage:
  - id: D1
    description: "A card can be deleted from its menu: it vanishes at once with 'Card deleted', the row stays with deleted_at, and a failed delete brings it back in place with a message"
    requirement: CARD-03
    verification:
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_delete_removes_the_card_at_once_with_a_toast_and_soft_deletes"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_failed_delete_brings_the_card_back_between_its_neighbours"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_actions_live.py#test_move_and_delete_show_live_and_keep_the_row"
        status: pass
    human_judgment: false
  - id: D2
    description: "Deleting an already deleted card, or two simultaneous deletes, is a quiet no-op: one effect, no error, deleted_at keeps its first value"
    requirement: CARD-03
    verification:
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_fake_soft_delete_stamps_deleted_at_keeps_the_row_and_is_idempotent"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_deleting_a_card_already_deleted_elsewhere_is_quiet_and_it_stays_gone"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_actions_live.py#test_concurrent_deletes_are_idempotent"
        status: pass
    human_judgment: false
  - id: D3
    description: "A card can be moved from its menu to the end of one of the three other quadrants, at once for the actor, live for everyone else, rolled back with a message on failure; its author and edit state never change"
    requirement: CARD-04
    verification:
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_move_goes_to_the_end_of_the_target_at_once_and_the_old_quadrant_empties"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_failed_move_puts_the_card_back_at_its_old_position"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_moving_never_adds_edited_and_keeps_the_author"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_actions_live.py#test_move_and_delete_show_live_and_keep_the_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "A move into a quadrant of another session is refused by the database with SQLSTATE 23503 and changes nothing"
    requirement: CARD-04
    verification:
      - kind: integration
        ref: "tests/integration/test_card_actions_live.py#test_move_into_another_sessions_quadrant_is_rejected"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_move_into_a_quadrant_of_another_session_is_rejected_and_changes_nothing"
        status: pass
    human_judgment: false
  - id: D5
    description: "Repeated clicks and echoes never double-write or duplicate a card: one write per card in flight, the same element after a move, a deleted card never reappears"
    requirement: CARD-08
    verification:
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_two_delete_clicks_before_the_write_returns_write_once"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_two_move_clicks_before_the_write_returns_write_once"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_actions.py#test_the_card_element_survives_the_move_and_the_echo_shows_it_once"
        status: pass
    human_judgment: false
  - id: D6
    description: "In a real browser the Move to submenu opens on hover or tap beside the menu, and the move and delete feel instant in two windows"
    requirement: CARD-04
    verification: []
    human_judgment: true
    rationale: "The simulated user clicks items directly and cannot show how Quasar positions the nested menu or how fast it feels; this is the plan's end-of-phase human-check"

# Metrics
duration: 8min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 04: Card Delete and Move Summary

**Soft delete and move-to-end for cards from the card menu (Edit, Move to submenu, Delete), instant for the actor with rollback on failure, proven live against hosted Supabase including concurrent deletes and the composite FK refusing another session's quadrant**

## Performance

- **Duration:** 8 min
- **Started:** 2026-10-23T16:54:00Z
- **Completed:** 2026-10-23T17:02:00Z
- **Tasks:** 3
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- Delete: the menu item removes the card and shows "Card deleted" before the write returns; the row stays with `deleted_at`; a repeat or a racing second delete returns None and is treated as success; a failed write restores the card between its neighbours with "Could not delete the card. Please try again."
- Move to: a submenu lists the three other quadrants by label; the card jumps to the end of the chosen quadrant (highest order_index + 1024, 1024 when empty) at once; a failed write puts it back at its old position with "Could not move the card. Please try again."; the same card element is reused, no "(edited)" is added, the author is unchanged.
- Live proof against the hosted project: move and delete reach a second browser, deletes keep the row, two concurrent deletes both complete with exactly one effective, and a move into another session's quadrant fails with 23503 and changes nothing.

## Task Commits

Each task was committed atomically (TDD: RED test commit, then GREEN feat commit):

1. **Task 1: Delete from the card menu**
   - RED `e74d0d2` (test): 11 tests, all failing (missing `CARD_DELETED`/`DELETE_FAILED`, missing `delete_card`, no `card-action-delete` item)
   - GREEN `a6fc3d0` (feat): `soft_delete_card`, `delete_card`, Delete item with optimistic removal, toast and rollback
2. **Task 2: Move to another quadrant**
   - RED `e406a8b` (test): 15 new tests failing, the 11 delete tests still passing (missing `MOVE_FAILED`, missing `move_card`, no Move to item)
   - GREEN `0d0fecd` (feat): `move_card` in repository and service, Move to submenu, `_move_card` optimistic handler
3. **Task 3: Live proof** - `bffbc6d` (test): three integration tests, 3 passed, 0 skipped

**Plan metadata:** recorded in the docs commit that follows this summary.

## RED evidence (which tests failed before implementation)

- Task 1 (`uv run pytest tests/ui/test_card_actions.py -q` after the RED commit): 11 failed. The pinned-messages test failed with `AttributeError` on `app.ui.canvas_view.CARD_DELETED`; the two service tests failed with `AttributeError` on `delete_card`; the eight browser tests failed with "expected to find at least one element with marker='card-action-delete'" (the menu held only Edit). Constants are read as module attributes (`cv.CARD_DELETED`) so each test fails on its own assertion instead of one collection error.
- Task 2: 15 failed, 11 passed (the delete tests). The failing set was the pinned `MOVE_FAILED` test, the five service/fake move tests (`AttributeError: move_card`), the menu-order test (menu held Edit, Delete only) and the eight browser move tests (no `card-action-move-*` markers).
- Not run as RED: the three live tests of Task 3 only exercise code from Tasks 1 and 2 against the hosted project, so they were written after it and passed first time.

## Observed live propagation (hosted Supabase, polled every 100 ms by the test browser)

- Move chosen in browser A: A shows the card in DOES after 111 ms (poll granularity, effectively at once); browser B shows it in DOES below "Anchor" after 1129 ms.
- Delete chosen in browser A: A drops the card at once with "Card deleted"; browser B no longer shows it after 511 ms.
- Re-ran 03-01..03-03 live tests: 6 passed (2 in `test_live_card_edits.py`, 4 in `test_card_edit_storage.py`).

## Files Created/Modified

- `app/db/repository.py` - `soft_delete_card` (sets only `deleted_at`) and `move_card` (sets only `quadrant_id` and `order_index`), both through `_update_live_card`; no hard-delete call
- `app/services/sessions.py` - `delete_card` (row or None) and `move_card` (max_order_index + next_order_index, `CardGone` on None)
- `app/ui/canvas_view.py` - `CARD_DELETED`, `DELETE_FAILED`, `MOVE_FAILED`; Move to submenu and Delete item in `_build_menu`; `_delete_card`, `_move_card`; `_write` removes the card on a None result; `_render` hides the current quadrant's move item
- `tests/ui/fakes.py` - `FakeRepository.soft_delete_card` and `move_card` (the module-level `soft_delete_card` helper is unchanged)
- `tests/ui/test_card_actions.py` - 26 offline tests for delete and move
- `tests/integration/test_card_actions_live.py` - 3 live tests

## Decisions Made

See `key-decisions` above. In short: None means success for deletes; the toast shows with the optimistic removal; Move to is a submenu with the current quadrant's item hidden; no tombstone layer was added for deleted cards.

## Deviations from Plan

None - plan executed exactly as written.

Two small test-design choices worth noting, neither a deviation: the double-click proofs fire two synchronous clicks before any await (the real race) instead of firing a captured handler; and `test_card_actions.py` reads the constants as `cv.NAME` so a missing constant fails an assertion instead of breaking collection. The delete part has 11 tests (plan minimum 8) and the file 26 (plan minimum 17).

**Total deviations:** 0
**Impact on plan:** none.

## Issues Encountered

None. All tests passed on the first GREEN run of each task.

## Known Stubs

None.

## Threat Flags

None. T-03-11 (foreign-quadrant move), T-03-12 (hard delete) and T-03-14 (duplicate clicks) are mitigated and proven; no packages were installed (`pyproject.toml` and `uv.lock` unchanged).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 03-05 can insert Move up and Move down between Move to and Delete in `_build_menu`; `_move_card`'s optimistic placement and `_write` are reusable for reorder.
- Outstanding for end-of-phase verification: the two-window human check (D6) that the Move to submenu opens by hover or tap and that move and delete feel instant.

## Self-Check: PASSED

- Created files exist: `tests/ui/test_card_actions.py`, `tests/integration/test_card_actions_live.py`
- Commits found on HEAD: e74d0d2, a6fc3d0, e406a8b, 0d0fecd, bffbc6d
- `uv run pytest -q`: 252 passed; `uv run ruff check .` and `uv run ruff format --check .` clean; no `delete()` call in `app/db/repository.py`
- `uv run pytest -m integration tests/integration/test_card_actions_live.py -q -rs`: 3 passed, 0 skipped

---
*Phase: 03-card-editing*
*Completed: 2026-10-23*
