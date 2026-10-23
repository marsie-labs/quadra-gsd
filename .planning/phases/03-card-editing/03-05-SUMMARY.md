---
phase: 03-card-editing
plan: 05
subsystem: ui
tags: [nicegui, reorder, gapped-ordering, optimistic-ui, realtime, supabase, pytest, tdd]

requires:
  - phase: 03-card-editing
    provides: "03-01 projection model (optimistic overlay, in-place _render, guarded _write, _update_live_card), 03-03 card menu builder, 03-04 move/delete items, CardGone and the trigger-mirroring fake"
provides:
  - "reorder_index: pure ordering rule (midpoint of the passed neighbour and the next strictly different order_index, edge +/- 1024, None for edge/absent/exhausted)"
  - "SessionService.reorder_card: reads the card and the quadrant order from the database, writes exactly one order_index, no write at an edge"
  - "Repository.get_card, list_quadrant_order, set_card_order (all scoped by workspace and deleted_at is null)"
  - "Card menu in its full D-07 shape: Edit, Move to, Move up, Move down, Delete; markers card-action-up and card-action-down"
  - "D-10 enabled states (first card cannot move up, last cannot move down, a single card neither) refreshed on every render, local or remote"
  - "Live proofs against hosted Supabase and the README 'Editing cards' section covering every card action"
affects: [phase-04-close-session, phase-05-agent-snapshot]

actuals:
  tokens: 11900
  tasks: 2
  commits: 3

plan_head_before: 44a7f11801919912f2f10fc7a0b5d2480298227e
plan_head_after: 3e45ec07b23fb97ee8d5bbe73db3f21f216693df

tech-stack:
  added: []
  patterns:
    - "Reorder is a single-row midpoint write; no quadrant is ever renumbered, ties are passed as a group so the card really overtakes its neighbour"
    - "The service decides from the database order, the UI previews with the same pure function over what it shows, so both agree whenever the screen is current"
    - "_refresh_quadrant replaces _refresh_hint: one place updates the empty hint and the Move up/down enabled state of every card in a quadrant"

key-files:
  created:
    - tests/ui/test_card_reorder.py
    - tests/integration/test_card_reorder_live.py
  modified:
    - app/services/sessions.py
    - app/db/repository.py
    - app/ui/canvas_view.py
    - tests/ui/fakes.py
    - tests/ui/test_card_actions.py
    - README.md

key-decisions:
  - "Precision exhaustion is a silent no-op (nothing written) rather than a renumber, as CONTEXT forbids renumbering"
  - "Concurrent reorders are last-write-wins per row; convergence comes from one sort key (order_index, created_at, id) shared by UI, list_cards and the agent"
  - "Move up/down use set_enabled so the items stay visible and can be re-enabled when a remote change alters the quadrant order"

patterns-established:
  - "Disabled-but-visible menu items whose state is recomputed from the quadrant's shown order on every render"

requirements-completed: [CARD-05, CARD-08]

coverage:
  - id: D1
    description: "Move up / Move down swaps a card with its neighbour at once, writes exactly one order_index and converges across clients and reloads"
    requirement: CARD-05
    verification:
      - kind: unit
        ref: "tests/ui/test_card_reorder.py#test_reorder_index_places_the_card_between_its_new_neighbours"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_card_reorder.py#test_move_up_swaps_at_once_keeps_the_card_element_and_writes_one_row"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_reorder_live.py#test_reorder_shows_live_and_survives_reload"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_reorder_live.py#test_reorder_writes_exactly_one_row"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_reorder_live.py#test_concurrent_reorders_converge"
        status: pass
    human_judgment: false
  - id: D2
    description: "Edge items are disabled (D-10) and follow every change of the quadrant's order; the menu has the full D-07 shape"
    requirement: CARD-05
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_card_reorder.py#test_edge_items_are_disabled_and_stay_in_the_menu"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_card_reorder.py#test_a_remote_insert_at_the_end_enables_move_down_on_the_previous_last_card"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_card_reorder.py#test_menu_holds_edit_move_to_move_up_move_down_delete_in_that_order"
        status: pass
    human_judgment: false
  - id: D3
    description: "A failed reorder puts the card back and shows 'Could not move the card. Please try again.'; a double click writes once"
    requirement: CARD-08
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_card_reorder.py#test_failed_reorder_puts_the_card_back_and_shows_the_message"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_card_reorder.py#test_two_move_clicks_before_the_write_returns_write_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "Two writers updating one card at once end on the newest updated_at (backstop: the test cannot force the race to overlap in the database)"
    verification:
      - kind: integration
        ref: "tests/integration/test_card_reorder_live.py#test_racing_updates_of_one_card_end_on_the_newest_stamp"
        status: pass
    human_judgment: true
    rationale: "Backstop truth by plan design: the outcome is proven either way, but real overlap inside the database cannot be forced from a test"
  - id: D5
    description: "README 'Editing cards' section documents every card action"
    verification: []
    human_judgment: true
    rationale: "Documentation wording and the two-window visual check (greyed edges, live order in the second window) need a human read; the plan's human-check is harvested at end of phase"

duration: 7min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 5: Card Reorder Summary

**Move up / Move down for cards: a pure midpoint ordering rule, a one-row database write computed from the database's own order, D-10 disabled edge items, optimistic UI with rollback, and live Supabase proofs that reorders converge across browsers and reloads.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-23T17:04:35Z
- **Completed:** 2026-10-23T17:11:11Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- `reorder_index` skips tie groups so a card really passes its neighbour, returns the midpoint between the passed neighbour and the next strictly different value, uses +/- `ORDER_GAP` at an edge and returns `None` for an edge, an absent card or an exhausted gap.
- `SessionService.reorder_card` reads the card and its quadrant's order from the database, then writes exactly one `order_index`; at an edge it writes nothing and returns the card unchanged.
- The card menu now holds Edit, Move to, Move up, Move down, Delete. `_refresh_quadrant` disables Move up on the first card and Move down on the last (both on a single card) after every render, so remote inserts, moves and deletes keep the states correct.
- Live against hosted Supabase: a reorder shows in a second browser and after a reload, writes a single row, concurrent reorders converge and racing updates end on the newest stamp. The README documents every card action.

## RED evidence

`uv run pytest tests/ui/test_card_reorder.py` before any implementation: 30 failed, 1 passed (the pinned-message test). `gsd_run check tdd-red-evidence` on the unchanged JUnit report returned `RED_EVIDENCE_OK` / `target_test_failed` for the target `test_reorder_card_writes_once_and_changes_only_the_moved_order_index`. Semantic assessment: the target ran and failed on the planned behaviour, `reorder_card` / `reorder_index` / the menu items did not exist (`AttributeError` inside the test body, not a collection or fixture fault; the fake's new `get_card`, `list_quadrant_order`, `set_card_order` were committed with the tests).

RED before implementation (30 tests):

- all 14 parametrized `test_reorder_index_places_the_card_between_its_new_neighbours` cases
- `test_reorder_card_writes_once_and_changes_only_the_moved_order_index`
- `test_reorder_card_at_the_edge_writes_nothing_and_returns_the_card_unchanged`
- `test_reorder_card_decides_from_the_database_not_from_the_browser`
- `test_reorder_card_of_a_deleted_unknown_or_foreign_card_raises_card_gone`
- `test_reorder_card_rejects_an_unknown_direction_before_any_read`
- `test_menu_holds_edit_move_to_move_up_move_down_delete_in_that_order`
- `test_edge_items_are_disabled_and_stay_in_the_menu`
- `test_a_single_card_has_both_items_disabled`
- `test_move_up_swaps_at_once_keeps_the_card_element_and_writes_one_row`
- `test_move_down_swaps_with_the_next_card`
- `test_enabled_states_follow_the_new_order_after_a_move`
- `test_a_remote_insert_at_the_end_enables_move_down_on_the_previous_last_card`
- `test_a_remote_move_out_of_the_quadrant_updates_the_remaining_cards`
- `test_failed_reorder_puts_the_card_back_and_shows_the_message`
- `test_two_move_clicks_before_the_write_returns_write_once`
- `test_reordering_never_adds_edited_keeps_the_author_and_needs_no_name`

After GREEN: 31 passed in that file.

## Live results

- Race test printed timestamps (`test_racing_updates_of_one_card_end_on_the_newest_stamp`):
  - race A `updated_at=2026-10-23T17:08:07.659379+00:00`
  - race B `updated_at=2026-10-23T17:08:07.663205+00:00`
  - The stored row equals the newer one (B) in text and `updated_at`.
- Concurrent reorders converged on `['card 1', 'card 0', 'card 3', 'card 2']`: both moved cards computed 2560.0, a deliberate tie, and the shared sort key (`created_at` then id) placed card 0 before card 3 identically in both listeners and in `list_cards`.
- Reorder live file: 4 passed, 0 skipped. Combined live files (2 + 4 + 3 + 3 + 3): 15 passed, 0 skipped.
- Whole live suite at phase end (`uv run pytest -m integration -q -rs`): 35 passed, 0 failed, 0 skipped.
- Offline `uv run pytest -q`: 283 passed; `ruff check` and `ruff format --check` clean; no `ui.timer(` under `app`, no `ui.html`/`ui.markdown` under `app/ui`.

## Task Commits

1. **Task 1 RED: failing tests for card reorder** - `daa3d99` (test)
2. **Task 1 GREEN: move a card up or down within its quadrant** - `269dda1` (feat)
3. **Task 2: live reorder proofs and README Editing cards section** - `3e45ec0` (test)

**Plan metadata:** recorded in the docs commit that follows this file (docs: complete plan)

No REFACTOR commit: the implementation needed no cleanup after GREEN.

## Files Created/Modified

- `app/services/sessions.py` - `reorder_index` and `SessionService.reorder_card`
- `app/db/repository.py` - `get_card`, `list_quadrant_order`, `set_card_order`
- `app/ui/canvas_view.py` - Move up/down items, `_reorder_card`, `_quadrant_cards`, `_refresh_quadrant`
- `tests/ui/fakes.py` - fake `get_card`, `list_quadrant_order`, `set_card_order`
- `tests/ui/test_card_reorder.py` - 31 tests: pure rule, service on fake, menu in a simulated browser
- `tests/ui/test_card_actions.py` - menu-order assertion superseded by the five-item shape (as the plan directs)
- `tests/integration/test_card_reorder_live.py` - four live proofs
- `README.md` - scope sentence, `## Editing cards`, SQL "(edited)" note, new live test files

## Decisions Made

- Precision exhaustion is a silent no-op, never a renumber (CONTEXT forbids renumbering; about 50 halvings of one gap are needed to reach it).
- Last-write-wins per row for concurrent reorders; convergence is guaranteed by one shared sort key, not by merging intents.
- `set_enabled` rather than removing items keeps the D-10 items visible and re-enableable.

## Deviations from Plan

None - plan executed exactly as written. The only edit outside the plan's file list is the 03-04 menu-order test update in `tests/ui/test_card_actions.py`, which the plan itself prescribes ("the menu-order assertion in this task supersedes any 03-04 assertion").

**Total deviations:** 0
**Impact on plan:** none.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. The new reads and the order write are scoped by `workspace_id` and `deleted_at is null` (T-03-16), write one row (T-03-15) and rely on one deterministic sort key (T-03-17); no packages were installed (T-03-SC).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 3 is complete: edit, delete, move and reorder all converge across clients; cards keep stable ordering for the agent snapshot.
- End-of-phase human check (from the plan): two windows on one session, add three cards to IS, use Move up/Move down in window A, window B shows the same order within about a second and after a reload, the first card's Move up and the last card's Move down are greyed out, then a quick pass of every README "Editing cards" action.

## Self-Check: PASSED

- Files: `tests/ui/test_card_reorder.py`, `tests/integration/test_card_reorder_live.py`, `app/services/sessions.py`, `app/db/repository.py`, `app/ui/canvas_view.py`, `tests/ui/fakes.py`, `README.md` all present.
- Commits `daa3d99`, `269dda1`, `3e45ec0` are ancestors of HEAD.

---
*Phase: 03-card-editing*
*Completed: 2026-10-23*
