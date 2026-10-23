---
phase: 03-card-editing
plan: 02
subsystem: testing
tags: [nicegui, supabase, postgres-trigger, optimistic-ui, fake-repository, pytest]

requires:
  - phase: 03-card-editing
    provides: "03-01 tracer: cards_touch trigger, edit_card/CardGone, CanvasView _write/_optimistic/inline editor"
provides:
  - "CanvasView._write drops a card deleted meanwhile (CardGone) and warns 'This card was deleted.'"
  - "CanvasView._notify(message, type='warning')"
  - "FakeRepository.update_card_text with a cards_touch-mirroring _touch, update_calls, update_gate, fail_next_update_codes; seed_card(text_updated_at=...)"
  - "Offline edit proofs (tests/ui/test_card_editing.py) and hosted trigger/scoping proofs (tests/integration/test_card_edit_storage.py)"
affects: [03-03, 03-04, 03-05, phase-05-agent-snapshot]

actuals:
  tokens: 7800
  tasks: 2
  commits: 3

plan_head_before: 49cc509cfdb57e837a629bf10fdbfbace2b91b9b
plan_head_after: 6fcde5a193d35bf3e582555647cffc6c82b97c81

tech-stack:
  added: []
  patterns:
    - "Fake repository mirrors DB triggers (_touch) so offline write tests see the rows hosted Supabase returns"
    - "Tests wait on the repository effect (update_calls / stored text), never on should_see alone, because should_see also matches a textarea's value"

key-files:
  created:
    - tests/ui/test_card_editing.py
    - tests/integration/test_card_edit_storage.py
  modified:
    - tests/ui/fakes.py
    - app/ui/canvas_view.py

key-decisions:
  - "CardGone is handled in _write before the generic failure branch: the card is removed (not rolled back) and a warning, not an error, is shown"
  - "_notify gains a type parameter with default 'warning' so the resync message is unchanged"
  - "The fake applies the trigger's two rules in one _touch helper reused by every later fake write"

requirements-completed: [CARD-02, CARD-08]

coverage:
  - id: D1
    description: "Invalid edit text (empty, spaces, 501 code points) keeps the editor open with the shared error and makes no repository call; 500 code points saves; markup is shown literally"
    requirement: CARD-02
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_invalid_edit_keeps_editor_open_and_writes_nothing"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_edit_of_500_code_points_saves"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_edited_markup_is_shown_literally"
        status: pass
    human_judgment: false
  - id: D2
    description: "The acting participant sees the edit and '(edited)' before the write returns; confirmation and Realtime echo leave the same card element in place with no duplicate; a stale echo changes nothing"
    requirement: CARD-08
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_own_edit_shows_before_the_write_returns_and_is_never_rebuilt"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_editing_by_id_leaves_a_card_with_identical_text_alone"
        status: pass
    human_judgment: false
  - id: D3
    description: "A failed edit write returns the card to its last confirmed text and marker with a negative notification and stays editable"
    requirement: CARD-08
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_failed_edit_rolls_back_with_a_message_and_stays_editable"
        status: pass
    human_judgment: false
  - id: D4
    description: "Saving an edit of a card soft-deleted meanwhile removes it and shows 'This card was deleted.' as a warning"
    requirement: CARD-08
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_edit_of_a_card_deleted_meanwhile_drops_it_with_a_warning"
        status: pass
    human_judgment: false
  - id: D5
    description: "'(edited)' follows text_updated_at only (not quadrant/order changes) and survives reopening the canvas"
    requirement: CARD-02
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_marker_follows_text_updated_at_not_other_changes"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_reopened_canvas_shows_the_marker_for_an_edited_card"
        status: pass
    human_judgment: false
  - id: D6
    description: "Against hosted Supabase the cards_touch trigger gives every update a strictly newer updated_at, sets text_updated_at only on a real text change, and cannot be rewound, forged or cleared by a writer; edit_card refuses foreign-session and deleted cards without touching them"
    requirement: CARD-02
    verification:
      - kind: integration
        ref: "tests/integration/test_card_edit_storage.py#test_text_update_stamps_text_updated_at"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_edit_storage.py#test_non_text_updates_keep_text_updated_at"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_edit_storage.py#test_writer_cannot_rewind_or_forge_timestamps"
        status: pass
      - kind: integration
        ref: "tests/integration/test_card_edit_storage.py#test_edit_card_service_scoping"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 02: Edit Edge Hardening Summary

**CardGone handling in CanvasView._write, a trigger-mirroring FakeRepository.update_card_text, 22 offline edit-edge tests, and 4 hosted-Supabase proofs of the cards_touch timestamp rules and edit_card session scoping**

## Performance

- **Duration:** 5 min
- **Started:** 2026-10-23T16:38:28Z
- **Completed:** 2026-10-23T16:43:29Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `_write` catches `CardGone` before the generic branch: the card is removed and "This card was deleted." shows as a warning; it never reappears from that path.
- `FakeRepository` now supports card updates; `_touch` applies the trigger's `updated_at` floor (later of now and old + 1 microsecond) and the "text_updated_at only on a real text change" rule, so later plans can test writes offline.
- `tests/ui/test_card_editing.py` (22 tests): fake semantics, `edit_card` validation/scoping on the fake, `card_meta_text`, and the browser flows (optimistic display, stale echo ignored, same element after confirmation and echo, rollback with a negative notification, invalid text, 500 code points, deleted meanwhile, marker rules, identical-text cards, literal markup).
- `tests/integration/test_card_edit_storage.py` (4 tests) passes against the hosted project.

## Task Commits

1. **Task 1 RED: failing edit edge tests** - `266445b` (test)
2. **Task 1 GREEN: CardGone handling and trigger-mirroring fake** - `07eb4c0` (feat)
3. **Task 2: trigger timestamp rules and edit_card scoping against hosted Supabase** - `6fcde5a` (test)

**Plan metadata:** committed after this file (docs: complete plan)

## TDD evidence (Task 1)

RED run at `266445b`: 19 failed, 2 passed. Tests RED before implementation: all four `test_fake_update_*` tests, the three parametrized `test_edit_card_rejects_invalid_text_before_any_write` cases, `test_edit_card_trims_stores_500_code_points_and_keeps_author`, `test_edit_card_unknown_foreign_or_deleted_card_raises_card_gone`, `test_enter_saves_new_text_with_edited_marker_and_keeps_author`, `test_own_edit_shows_before_the_write_returns_and_is_never_rebuilt`, `test_failed_edit_rolls_back_with_a_message_and_stays_editable`, both `test_invalid_edit_keeps_editor_open_and_writes_nothing` cases, `test_edit_of_500_code_points_saves`, `test_edit_of_a_card_deleted_meanwhile_drops_it_with_a_warning`, `test_reopened_canvas_shows_the_marker_for_an_edited_card`, `test_editing_by_id_leaves_a_card_with_identical_text_alone` and `test_edited_markup_is_shown_literally`. They failed because `FakeRepository` had no `update_card_text`/`update_calls`/`seed_card(text_updated_at=)` (AttributeError/TypeError), and the CardGone test additionally because `_write` had no `CardGone` branch. Already green before implementation (03-01 behavior): `test_card_meta_text_marks_edits_only_when_text_updated_at_is_set` and `test_marker_follows_text_updated_at_not_other_changes`. Note: the test-first commit was done by hand per the plan's TDD flag (the project has no `workflow.tdd_mode`), so the RED evidence is the failing run above, not a `check tdd-red-evidence` record. After the later wait-helper fixes, GREEN run: 22 passed, stable across 3 runs.

## Task 2 against Remote

`uv run pytest -m integration tests/integration/test_card_edit_storage.py tests/integration/test_card_storage.py tests/integration/test_live_cards.py -q -rs` -> **10 passed, 0 skipped** (4 new storage tests ran against the hosted Supabase project, plus 3 Phase 2 storage and 3 Phase 2 live tests). Full offline suite: 201 passed; `ruff check` and `ruff format --check` clean.

## Files Created/Modified
- `tests/ui/test_card_editing.py` - offline edit proofs
- `tests/integration/test_card_edit_storage.py` - live trigger and scoping proofs
- `tests/ui/fakes.py` - `update_card_text`, `_touch`, `update_calls`, `update_gate`, `fail_next_update_codes`, `seed_card(text_updated_at=...)`, `text_updated_at` on inserted cards
- `app/ui/canvas_view.py` - `except CardGone` branch in `_write`; `_notify(message, type="warning")`

## Decisions Made
- CardGone removes the card instead of rolling back to the last server row, because the row no longer exists in the session; the message is a warning since nothing was lost by the participant's error.
- Notification types are asserted in tests through a `UserNotify` subclass assigned to `user.notify`, because the NiceGUI user plugin re-binds `ui.notify` on every `user` attribute access, so patching `ui.notify` does not stick.

## Deviations from Plan

None - plan executed exactly as written. One test-design adjustment (not a code deviation): the plan's behavior list implies "the new text shows" checks, but `user.should_see(text)` also matches a textarea's value, so it cannot distinguish a typed edit from a saved one. The tests instead wait on the repository effect (`update_calls`, stored text) through a local `_wait_for` helper and then assert on the card labels.

**Total deviations:** 0 auto-fixed.

## Issues Encountered
- First GREEN run had 4 failing UI tests caused by the `should_see`/textarea-value ambiguity above and by `user.find(marker="card")` raising when no card remains; fixed in the tests (wait helper, `_card_count` counting column children). No production-code change was needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `FakeRepository._touch` and the update gate/fail-code fields are ready for 03-03 to 03-05 (delete, move, reorder) offline write tests.
- No stubs, no new dependencies, no new network or auth surface.

## Self-Check: PASSED

- `tests/ui/test_card_editing.py`, `tests/integration/test_card_edit_storage.py`, `tests/ui/fakes.py`, `app/ui/canvas_view.py` exist.
- Commits `266445b`, `07eb4c0`, `6fcde5a` are ancestors of HEAD.
- Acceptance greps: `update_gate`, `fail_next_update_codes`, `def update_card_text`, `def _touch`, `text_updated_at` in fakes.py; `except CardGone` in canvas_view.py; `keydown.enter.exact.prevent`, `Could not save the card. Please try again.`, `This card was deleted.` in test_card_editing.py; the four integration test names present.

---
*Phase: 03-card-editing*
*Completed: 2026-10-23*
