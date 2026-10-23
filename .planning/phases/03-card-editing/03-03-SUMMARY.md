---
phase: 03-card-editing
plan: 03
subsystem: ui
tags: [nicegui, inline-editing, optimistic-ui, realtime, d-04, pytest]

requires:
  - phase: 03-card-editing
    provides: "03-01 tracer (cards_touch trigger, edit_card, CanvasView _write/_optimistic/_render, inline editor) and 03-02 edge hardening (CardGone, trigger-mirroring fake)"
provides:
  - "One always-visible more_vert menu button per card (marker card-menu) with a text-derived aria-label and an Edit item (marker card-action-edit); CanvasView._build_menu is the single builder 03-04/03-05 extend in D-07 order"
  - "Sticky-note editor rules: Enter (keydown.enter.exact.prevent) saves, Shift+Enter adds a line, blur saves valid changed text, Esc (_cancel_edit) cancels, unchanged text writes nothing, invalid text keeps the editor open, repeats write once"
  - "D-04 draft protection proven: remote edits, resyncs and remote moves keep the open textarea and draft; a remote delete closes the editor with the warning 'This card was deleted.'"
  - "Menu button disabled while the card's write is in flight"
affects: [03-04, 03-05, phase-05-agent-snapshot]

actuals:
  tokens: 8600
  tasks: 2
  commits: 4

plan_head_before: 9f8a59df94bbee6684d53d9ff2dbe8b2885d54e4
plan_head_after: 74c1efc4d9cb34b71398c2d473711f13c2e23d18

tech-stack:
  added: []
  patterns:
    - "The open edit session is the done flag: whichever of Enter, Esc or blur closes it first wins, the others find no session and return"
    - "Menu button accessible name set by props item assignment (never the props string parser) because the text is user input"
    - "_remove is the single place a deleted card's open editor is closed and the participant warned"
    - "Test-side remote change: write the change into the fake DB through _touch and return that row as the event, so a later confirmed save compares against a coherent updated_at"

key-files:
  created:
    - tests/ui/test_edit_concurrency.py
  modified:
    - app/ui/canvas_view.py
    - tests/ui/test_card_editing.py
    - tests/integration/test_live_card_edits.py

key-decisions:
  - "The card menu gets Quasar's no-refocus prop so closing it after Edit cannot hand focus back to the button while the new editor takes it (a refocus would blur the editor and, being unchanged, close it at once)"
  - "_cancel_edit is a plain def (the plan allowed either): Esc needs no await"
  - "Unchanged-text check runs before the busy check: opening and closing an editor without typing never writes and never reverts someone else's change"

patterns-established:
  - "menu_label(text): 'Card actions: ' + first 40 code points, refreshed by _render when the shown text changes"
  - "_close_editor + _render is how Esc shows the latest known text; _render only ever updates a card that has an open editor, never rebuilds it"

requirements-completed: [CARD-02, CARD-08]

coverage:
  - id: D1
    description: "Every card has one always-visible, enabled menu button whose accessible name carries the first 40 code points of its text; its Edit item opens the inline editor"
    requirement: CARD-02
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_every_card_has_one_enabled_menu_button_with_a_distinct_accessible_name"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_menu_edit_item_opens_the_editor_with_the_card_text"
        status: pass
    human_judgment: true
    rationale: "Touch opening of the menu and the Quasar menu/focus interplay run only in a real browser"
  - id: D2
    description: "Enter saves, Shift+Enter keeps a line break (exact modifier), blur saves valid changed text, Esc cancels, queued blur after Enter or Esc writes nothing more"
    requirement: CARD-02
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_editor_registers_one_exact_enter_listener_plus_esc_and_blur"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_multi_line_text_is_stored_with_its_line_break_and_shown_on_two_lines"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_blur_saves_changed_text"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_enter_then_a_queued_blur_writes_once"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_esc_then_a_queued_blur_writes_nothing"
        status: pass
    human_judgment: true
    rationale: "Vue's exact modifier letting Shift+Enter through, real focus loss on click-away and autofocus only run in a real browser"
  - id: D3
    description: "Unchanged, invalid and repeated submits: no write for unchanged text, editor stays open with the error for invalid text, double Enter writes once and disables the menu button, nameless participants edit without a dialog"
    requirement: CARD-08
    verification:
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_unchanged_text_padded_with_spaces_writes_nothing_and_closes_the_editor"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_blur_with_empty_text_keeps_the_editor_open_with_the_error_until_esc"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_double_enter_in_flight_writes_once_and_guards_the_card"
        status: pass
      - kind: unit
        ref: "tests/ui/test_card_editing.py#test_anyone_edits_without_a_name_and_the_author_stays"
        status: pass
    human_judgment: false
  - id: D4
    description: "An open draft survives a remote edit, a reconnect resync and a remote move of its card; Enter saves the draft (last save wins), Esc shows the remote text"
    requirement: CARD-02
    verification:
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_remote_edit_keeps_the_same_editor_and_draft_and_updates_the_hidden_text"
        status: pass
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_resync_keeps_the_editor_and_draft_and_esc_shows_the_database_text"
        status: pass
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_remote_move_keeps_the_editor_and_draft_in_the_new_column_and_enter_saves"
        status: pass
      - kind: integration
        ref: "tests/integration/test_live_card_edits.py#test_open_draft_survives_remote_edit_and_last_save_wins"
        status: pass
    human_judgment: true
    rationale: "Re-mounting a focused textarea after a card move may fire a browser blur; only two real windows show it"
  - id: D5
    description: "A remote delete (soft delete, DELETE event, resync without the card) closes the open editor and shows the warning 'This card was deleted.'"
    requirement: CARD-02
    verification:
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_soft_delete_event_closes_the_editor_and_warns"
        status: pass
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_delete_event_with_only_the_id_closes_the_editor_and_warns"
        status: pass
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_a_resync_without_the_card_closes_the_editor_and_warns"
        status: pass
    human_judgment: false
  - id: D6
    description: "During an in-flight save a stale echo changes nothing; once the save settles the row with the greater updated_at is shown on every screen"
    requirement: CARD-08
    verification:
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_stale_event_during_a_save_changes_nothing_on_screen"
        status: pass
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_a_remote_change_committed_after_the_save_wins_on_this_screen"
        status: pass
      - kind: unit
        ref: "tests/ui/test_edit_concurrency.py#test_a_remote_change_committed_before_the_save_loses_to_it"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 3: Card Menu and Sticky-Note Editing Summary

**Per-card more_vert menu with Edit, Enter/blur/Esc/Shift+Enter editor rules with a done-flag edit session, and D-04 draft protection proven offline and against hosted Supabase (open draft survives a remote edit, last save wins, remote delete closes the editor with a warning)**

## Performance

- **Duration:** 12 min
- **Started:** 2026-10-23T16:41:00Z
- **Completed:** 2026-10-23T16:53:00Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- Each card now has one always-visible `more_vert` button (works on touch, no hover-only control). Its accessible name is `Card actions: ` plus the first 40 code points of the card text and follows later edits. Its menu's first item, Edit, opens the inline editor; clicking the text still works.
- `_commit_edit` follows the specified order: no open session returns (the done flag), invalid text keeps the editor open with the error, unchanged text (against the text the editor opened with or the latest server text) closes without a write, a busy card keeps the editor open, otherwise the editor closes before the first await and `_write` runs. Enter, blur and Esc cannot write twice.
- `_cancel_edit` (Esc) closes the editor and shows the latest known text. `_write` disables the card's menu button while its write is in flight and re-enables it in `finally`.
- D-04: `_render` already updated an open-editor card in place (03-01), so a remote edit, a resync and a remote move keep the same textarea object and draft; only the missing piece was added: `_remove` now closes an open editor with its card and warns `This card was deleted.` (covers soft delete, DELETE event, resync without the card).
- Last save wins is proven around an in-flight save with the `updated_at` stale guard: a stale echo changes nothing, a later remote commit wins after the save settles, an earlier one loses.
- Live (hosted Supabase, two browsers): B's open draft survives A's edit, B's hidden label follows A's text through the Realtime echo, and B's Enter makes B's text the final text in A and in the database.

## Task Commits

1. **Task 1: sticky-note editing**
   - RED: `3632463` (test) - 11 new failing tests, 1 new regression test already green
   - GREEN: `bb54539` (feat)
2. **Task 2: D-04 draft protection**
   - RED: `b258883` (test) - 3 failing delete-warning tests, 9 concurrency tests and the live test already green
   - GREEN: `74c1efc` (feat) - `_remove` warning plus the typed-notify test helper fix

**Plan metadata:** committed separately after this file (docs: complete plan).

## TDD notes (which tests were RED before implementation)

`workflow.tdd_mode` is not enabled for this project and pytest produces no report format the `gsd_run check tdd-red-evidence` classifier supports, so the classifier was not run. RED was assessed semantically from the actual pytest output: every RED test failed on an assertion for the planned behavior (missing `card-menu` / `card-action-edit` markers, missing `keydown.esc` and `blur` listeners, editor not closing on Esc, no error on blur with empty text, missing menu button to disable, missing warning), never on a syntax, import or fixture error.

- Task 1, RED before implementation (11): `test_every_card_has_one_enabled_menu_button_with_a_distinct_accessible_name`, `test_menu_edit_item_opens_the_editor_with_the_card_text`, `test_editor_registers_one_exact_enter_listener_plus_esc_and_blur`, `test_blur_saves_changed_text`, `test_enter_then_a_queued_blur_writes_once`, `test_esc_then_a_queued_blur_writes_nothing`, `test_esc_closes_the_editor_and_shows_the_original_text`, `test_unchanged_text_padded_with_spaces_writes_nothing_and_closes_the_editor`, `test_blur_with_empty_text_keeps_the_editor_open_with_the_error_until_esc`, `test_double_enter_in_flight_writes_once_and_guards_the_card`, `test_anyone_edits_without_a_name_and_the_author_stays`.
- Task 1, green at once (1): `test_multi_line_text_is_stored_with_its_line_break_and_shown_on_two_lines` (the exact-modifier listener and `whitespace-pre-wrap` already existed from 03-01; kept as a regression proof).
- Task 2, RED before implementation (3, re-verified by reverting `_remove`): `test_soft_delete_event_closes_the_editor_and_warns`, `test_delete_event_with_only_the_id_closes_the_editor_and_warns`, `test_a_resync_without_the_card_closes_the_editor_and_warns`.
- Task 2, green at once (9 offline plus the live test): the remaining concurrency tests and `test_open_draft_survives_remote_edit_and_last_save_wins`. D-04 protection for edit, resync and move already followed from 03-01's in-place `_render`; these tests now pin it.

Two test fixes were made in the GREEN commits and are not RED evidence: the `_wait_for`/hidden-label wording in two Task 1 tests (a hidden label is invisible to `user.find`; `should_not_see` replaces a `find().elements` on an absent element) and the `_typed_notify` helper in the concurrency tests (see Issues Encountered).

## TDD Gate Compliance

RED (`test(03-03)`) precedes GREEN (`feat(03-03)`) for both tasks: `3632463` then `bb54539`, `b258883` then `74c1efc`. No refactor commits.

## Live LWW test observed timings (hosted Supabase, two simulated browsers)

Three runs of `uv run pytest -m integration tests/integration/test_live_card_edits.py -q -rs -s`, all `2 passed`, 0 skipped:

| Measurement | Run 1 | Run 2 |
|---|---|---|
| A presses Enter -> B's hidden label follows (B's editor still holds the draft) | not printed | 610 ms |
| B presses Enter -> A shows B's text | 508 ms | 510 ms |
| 03-01 tracer: edit Enter -> browser B shows the edit | not printed | 567 ms |

All within the 5 s bound; the bounded wait loops (at most 50 x 0.1 s) live only in the test, and `grep -rn "ui.timer(" app` finds nothing.

## Files Created/Modified

- `app/ui/canvas_view.py` - `menu_label`, `_CardWidgets.menu_button/menu`, `_build_menu`, `_cancel_edit`, blur and Esc listeners, new `_commit_edit` rules, busy cue on the menu button, `_remove` closes an open editor and warns
- `tests/ui/test_card_editing.py` - 12 new tests for the menu, listeners, Enter/blur/Esc/unchanged/invalid/double-submit/nameless rules (34 tests in the file)
- `tests/ui/test_edit_concurrency.py` - new, 13 tests for D-04 (remote edit, resync, move, delete, last save wins)
- `tests/integration/test_live_card_edits.py` - `test_open_draft_survives_remote_edit_and_last_save_wins`

## Decisions Made

- Added Quasar's `no-refocus` prop to the card menu (see Deviations).
- `_cancel_edit` is a plain `def`; the plan allowed `async def` or plain.
- The unchanged-text check precedes the busy check, as the plan's order specifies.
- A remote change in concurrency tests is stored in the fake DB through `FakeRepository._touch` before its event is fed to the hub, so the later confirmed save and the stale guard compare coherent `updated_at` values (a fabricated future `updated_at` that the DB never had made the confirmed save look stale).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `no-refocus` on the card menu**
- **Found during:** Task 1 (menu build, reading NiceGUI menu.py / Quasar QMenu behavior)
- **Issue:** Quasar's QMenu returns focus to its trigger when it hides. Edit opens an `autofocus` textarea at the same moment the menu closes, so the refocus could blur the editor straight away; with the new blur-saves rule that would close the unchanged editor immediately and make Edit look broken.
- **Fix:** `ui.menu().props("no-refocus")` in `_build_menu`.
- **Files modified:** app/ui/canvas_view.py
- **Verification:** menu/Edit tests pass offline; the focus behavior itself runs only in a real browser and stays in the end-of-phase human check.
- **Committed in:** bb54539

**2. [Rule 1 - Bug] Test helper swapped `user.notify` without making the swap effective**
- **Found during:** Task 2 (delete-warning tests)
- **Issue:** The `user` fixture re-points `ui.notify` at its notifier on every attribute access, so a notifier assigned right before a synchronous hub event never received the notification and the tests failed for a test-harness reason, not the missing product behavior.
- **Fix:** `_typed_notify(user)` assigns the notifier and touches `user.client` once; all three typed-notify tests use it. RED for the delete tests was re-verified afterwards by reverting `_remove`.
- **Files modified:** tests/ui/test_edit_concurrency.py
- **Committed in:** 74c1efc

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 test bug)
**Impact on plan:** No scope change. The `no-refocus` prop is a one-word hardening on a plan-specified element.

## Issues Encountered

- The first concurrency tests fabricated remote rows with `updated_at` +5 s that the fake DB did not hold; the save's confirmed row (stamped "now") then lost the stale guard and the screen kept the remote text. The product was right and the test was incoherent; fixed by storing remote changes in the fake first (`_remote_change`). Noted because the same trap awaits later plans that fabricate remote rows.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Threat Flags

None. No new network endpoints, auth paths or schema changes; no packages installed (`pyproject.toml` and `uv.lock` unchanged, T-03-SC). T-03-08 mitigated by the edit session as done flag, the per-card `_busy` guard and the disabled menu button (tests: double Enter, Enter then queued blur, Esc then queued blur). T-03-10 mitigated by item assignment of `aria-label` cut to 40 code points; no HTML or Markdown element under `app/ui`.

## End-of-phase human checks (real browser, `uv run python -m app`)

Not run here; the user fixture cannot execute them.

1. Open a card's menu (also with browser touch emulation), choose Edit, type two lines using Shift+Enter, press Enter: both lines show. Edit again and click elsewhere: it saves. Edit again and press Esc: old text returns. Clear the text and click away: the error appears and nothing is saved. Watch that choosing Edit leaves the editor open and focused (the `no-refocus` assumption).
2. Two windows on one session: in B start editing and type without saving; in A edit the same card and press Enter. B's editor keeps B's typing; Enter in B puts B's text in both windows. After 03-04 lands, delete the card from A: B's editor closes and shows "This card was deleted.". Also move the card from A while B edits and check B's editor does not blur-save unexpectedly.

## Next Phase Readiness

Ready for 03-04 (Move to and Delete): `_build_menu` is the single place to add `Move to` and `Delete` after `Edit` in the D-07 order, and `_remove` already handles a delete arriving while someone edits. No blockers.

## Self-Check: PASSED

Verified below by command: files exist, commits are ancestors of HEAD, full suite 226 passed, `uv run ruff check .` and `uv run ruff format --check .` clean, live command `2 passed` with 0 skipped.

---
*Phase: 03-card-editing*
*Completed: 2026-10-23*
