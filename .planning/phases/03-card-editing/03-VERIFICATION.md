---
phase: 03-card-editing
verified: 2026-10-23T18:00:00Z
status: human_needed
score: 5/6 must-haves verified
covered_files:
  - .planning/phases/03-card-editing/03-01-PLAN.md
  - .planning/phases/03-card-editing/03-01-SUMMARY.md
  - .planning/phases/03-card-editing/03-02-PLAN.md
  - .planning/phases/03-card-editing/03-02-SUMMARY.md
  - .planning/phases/03-card-editing/03-03-PLAN.md
  - .planning/phases/03-card-editing/03-03-SUMMARY.md
  - .planning/phases/03-card-editing/03-04-PLAN.md
  - .planning/phases/03-card-editing/03-04-SUMMARY.md
  - .planning/phases/03-card-editing/03-05-PLAN.md
  - .planning/phases/03-card-editing/03-05-SUMMARY.md
  - README.md
  - app/db/repository.py
  - app/models.py
  - app/services/sessions.py
  - app/ui/canvas_view.py
  - supabase/migrations/20261023120000_card_edit_tracking.sql
  - tests/ui/fakes.py
covered_digest: "v3:sha256:4e9a179e74578c1140f2433f9107bcac4b2f43395183be8889f3ccbc6b739f5d"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Two real browser windows on one session (uv run python -m app): click a card's text in window A, change it, press Enter. Reload window B."
    expected: "A shows the new text with '(edited)' at once; B shows the same within about 1 s without reload and still shows it after reload."
    why_human: "Visual/interaction feel and real-browser Realtime latency; the simulated user cannot judge it (plan 03-01 human-check)."
  - test: "Open a card's menu (also with touch emulation) and choose Edit; type two lines with Shift+Enter, press Enter; Edit again and click elsewhere; Edit again and press Esc; clear the text and click away."
    expected: "Editor takes focus with no refocus fight (menu has no-refocus); both lines show after Enter; blur saves; Esc restores the old text; empty text shows the error and saves nothing."
    why_human: "Real focus handling, Shift+Enter in a real textarea and Quasar menu behaviour are not exercised by the simulated browser (plan 03-03 human-check)."
  - test: "Two real windows: in B start editing a card without saving; in A edit the same card and press Enter; press Enter in B. Repeat but delete the card from A."
    expected: "B's editor and draft stay intact; after B's Enter both windows show B's text; on delete B's editor closes and shows 'This card was deleted.'"
    why_human: "Cross-window draft protection (D-04) in real browsers (plan 03-03 human-check)."
  - test: "Open a card's menu, hover or tap 'Move to', pick DOES; pick Delete on another card (two windows)."
    expected: "The Move to submenu opens beside the menu on hover and on tap; the card jumps to the bottom of DOES at once here and within about a second in the other window; Delete removes the card at once with 'Card deleted' in both."
    why_human: "Quasar nested-menu positioning and perceived instantness are not visible to the simulated user (plan 03-04 human-check)."
  - test: "Add three cards to IS; use Move up and Move down in window A; look at window B and reload."
    expected: "B shows the same order within about a second and after reload; the first card's Move up and the last card's Move down are greyed out (a single card has both greyed)."
    why_human: "Greyed-out rendering and live feel in real browsers (plan 03-05 human-check)."
  - test: "Backstop truth (insufficient_spec): two writers update the same card at the same moment (e.g. two windows saving an edit/reorder of one card simultaneously, or two scripted PostgREST updates fired in parallel against the hosted project, repeated)."
    expected: "The row's final updated_at is the newest of the two stamps and every client ends on that row."
    why_human: "Plan 03-05 tags this truth verification: backstop and states the test cannot force the two updates to overlap in the database. The wired test test_racing_updates_of_one_card_end_on_the_newest_stamp passes but only proves the outcome 'either way'; the verifier abstains on a non-inferable truth without forced-overlap evidence."
---

# Phase 3: Card Editing Verification Report

**Phase Goal:** Participants can edit, delete, move and reorder cards collaboratively, and their own actions feel instant.
**Verified:** 2026-10-23T18:00:00Z
**Status:** human_needed
**Re-verification:** No, initial verification

All automated evidence supports the goal; no FAILED truth and no blocker anti-pattern. The status is `human_needed` because the plans deliberately deferred real-browser checks to end of phase, and one plan truth is tagged `backstop` (non-inferable).

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Participant can edit a card's text; others see it live | VERIFIED | `canvas_view._start_edit/_commit_edit` -> `sessions.edit_card` -> `repository.update_card_text` (writes only `text`; scoped by id, workspace, `deleted_at is null`). `cards_touch` trigger stamps `updated_at`/`text_updated_at`. Hosted `test_card_edited_in_one_browser_shows_live_in_another` passed (browser B sees new text and "(edited)", row author/quadrant/order unchanged, trigger stamps equal). |
| 2 | Participant can delete a card; gone for everyone, row stays in DB with a deleted timestamp | VERIFIED | `repository.soft_delete_card` sets `deleted_at` via `_update_live_card` (no `.delete()` anywhere in `app/db`); idempotent (second call matches no row -> None). Hosted `test_move_and_delete_show_live_and_keep_the_row` and `test_concurrent_deletes_are_idempotent` passed. |
| 3 | Move to another quadrant via a move menu; leaves old quadrant, appears in new one for all clients | VERIFIED | "Move to" submenu in `_build_menu` (three other quadrants); `sessions.move_card` writes `quadrant_id` + `max+1024`; cross-session quadrant rejected by composite FK (23503). Hosted `test_move_and_delete_show_live...` and `test_move_into_another_sessions_quadrant_is_rejected` passed; UI tests assert the card element survives the move and shows once after the echo. |
| 4 | Reorder up/down within a quadrant; order matches across clients and after reload | VERIFIED | `reorder_index` (pure, tie-group aware) + `SessionService.reorder_card` computes from DB order and writes exactly one row (`set_card_order`). Hosted `test_reorder_shows_live_and_survives_reload`, `test_reorder_writes_exactly_one_row`, `test_concurrent_reorders_converge` passed. D-10 edge items disabled via `_refresh_quadrant`. |
| 5 | Actor sees change instantly, no duplicate/flicker when the echo arrives; failed write rolls back with a message | VERIFIED | `_write` applies an optimistic overlay (`_optimistic`) before awaiting, keeps one element per card id (`_render` updates in place), pops the overlay and re-renders with `EDIT_FAILED`/`DELETE_FAILED`/`MOVE_FAILED` negative notify on exception. UI tests assert held-write optimistic display, element identity (`is element_before`) and `_card_count == 1` after confirmed row + echo, and rollback messages for edit, delete, move and reorder. |
| 6 | (Plan 03-05, `verification: backstop`) Two simultaneous writers on one card end on the newest `updated_at` and every client converges | UNCERTAIN (insufficient_spec) | `cards_touch` uses `greatest(clock_timestamp(), old.updated_at + 1 microsecond)`; `test_writer_cannot_rewind_or_forge_timestamps` and `test_racing_updates_of_one_card_end_on_the_newest_stamp` pass, but the latter's own docstring says it cannot force the overlap. Routed to human verification (not a FAIL). |

**Score:** 5/6 truths verified (0 present-but-behavior-unverified; 1 backstop truth abstained)

Plan-level truths were also spot-checked against code and tests and none contradicts the above: menu order Edit, Move to, Move up, Move down, Delete (`test_menu_holds_edit_move_to_move_up_move_down_delete_in_that_order`); `keydown.enter.exact.prevent` listener (`test_editor_registers_one_exact_enter_listener_plus_esc_and_blur`); draft survives remote edit/resync/move and mid-edit delete warns (`tests/ui/test_edit_concurrency.py`, plus hosted `test_open_draft_survives_remote_edit_and_last_save_wins`); blur/Esc/unchanged/invalid editor rules; per-card `_busy` re-entrancy guard; no polling (`while True` only in the hub reconnect loop and `resync` single-flight rerun, both reactions to Realtime state, never a timer).

### Prohibitions (test-tier, enforcement wired)

| Prohibition | Enforcement found | Status |
|-------------|-------------------|--------|
| CARD-02: MUST NOT change/reattribute author on edit | No write path sets `author`; `test_enter_saves_new_text_with_edited_marker_and_keeps_author`, `test_edit_card_trims_stores_500_code_points_and_keeps_author`, live row assertion `author == "Ann"` | resolved |
| CARD-08: MUST NOT leave an optimistic change after failed write | `test_failed_edit_rolls_back...`, `test_failed_delete_brings_the_card_back...`, `test_failed_move_puts_the_card_back...`, `test_failed_reorder_puts_the_card_back...` | resolved |
| CARD-02: MUST NOT discard an open draft on remote change/resync/echo | `tests/ui/test_edit_concurrency.py` (keeps same editor element and draft) + hosted draft test | resolved |
| CARD-03: MUST NOT hard-delete a card row through the app | Repository has no delete call; `test_fake_soft_delete_stamps_deleted_at_keeps_the_row_and_is_idempotent`; hosted row-kept assertion | resolved |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261023120000_card_edit_tracking.sql` | `text_updated_at` + `cards_touch` BEFORE UPDATE trigger | VERIFIED | Substantive; `supabase migration list --linked` re-run by verifier shows 20261023120000 on Local and Remote. |
| `app/models.py` | `CardView.text_updated_at` | VERIFIED | Selected through `CARD_COLUMNS`; used by `card_meta_text`. |
| `app/db/repository.py` | update_card_text, soft_delete_card, move_card, get_card, list_quadrant_order, set_card_order | VERIFIED | All scoped by workspace and `deleted_at is null`. |
| `app/services/sessions.py` | CardGone, edit_card, delete_card, move_card, reorder_index, reorder_card | VERIFIED | Validation before any repository call; wired from `canvas_view`. |
| `app/ui/canvas_view.py` | In-place projection, optimistic overlay, editor, menu, D-10 | VERIFIED | 667 lines, no stubs; all handlers reach services via `_write`. |
| `tests/ui/*`, `tests/integration/*` (new files) | Offline and hosted proofs | VERIFIED | Present, substantive, run below. |
| `README.md` | Migration row, repair line, push-before-start note, "Editing cards" | VERIFIED | Rows/lines present (lines 57-66). |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| canvas_view editor Enter/blur | `sessions.edit_card` | `_commit_edit` -> `_write` lambda | WIRED |
| canvas_view Delete/Move/Up/Down | `sessions.delete_card/move_card/reorder_card` | `_delete_card/_move_card/_reorder_card` -> `_write` | WIRED |
| sessions -> repository | `update_card_text`, `soft_delete_card`, `move_card`, `set_card_order` | direct awaits | WIRED |
| repository -> migration | `text_updated_at` in `CARD_COLUMNS` | hosted tests read it back | WIRED |
| hub UPDATE events -> canvas | `apply_card` -> `_apply` -> in-place `_render` | stale guard on `updated_at` | WIRED |
| `_render` -> `_editing` | never rebuilds a card with an open editor | `_render` only updates labels/position | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| card text/meta labels | `CardView` rows | Supabase `cards` via PostgREST write return + Realtime echo + `list_cards` snapshot | Yes (hosted tests assert DB row and second-browser view) | FLOWING |
| Move up/down enabled state | `_quadrant_cards` ordering | shown rows (optimistic over server) | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Offline suite | `uv run pytest -q` | 283 passed, 35 deselected | PASS |
| Lint | `uv run ruff check app tests` | All checks passed | PASS |
| Hosted phase-3 integration tests | `uv run pytest -m integration` on the four phase-3 files | 13 passed (53.6 s) | PASS |
| Migration applied to hosted project | `supabase migration list --linked` | 20261023120000 local = remote | PASS |

### Probe Execution

Step 7c: SKIPPED. No `probe-*.sh` declared by the plans or present under `scripts/`.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| CARD-02 | 03-01, 03-02, 03-03 | Participant can edit a card's text | SATISFIED | Truth 1; editor rules and concurrency tests |
| CARD-03 | 03-04 | Participant can delete a card (soft-delete) | SATISFIED | Truth 2 |
| CARD-04 | 03-04 | Move a card to another quadrant via move menu | SATISFIED | Truth 3 |
| CARD-05 | 03-05 | Reorder within quadrant via up/down | SATISFIED | Truth 4 |
| CARD-08 | 03-01..03-05 | Own actions instant, no duplicates, failed writes roll back with message | SATISFIED | Truth 5 |

REQUIREMENTS.md maps exactly CARD-02, -03, -04, -05, -08 to Phase 3; all appear in plan frontmatter. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (phase files) | - | TBD/FIXME/XXX/TODO/HACK scan | none | No debt markers in `app/`, migration, tests, README. |
| `app/ui/canvas_view.py` | 546-554 | WR-01: draft lost when a save fails | Warning | Card rolls back and message shows (goal met), but the typed text is gone. Open in 03-REVIEW-DISPOSITION.md. |
| `app/ui/canvas_view.py` | 200-211 | WR-02: late echo of an earlier change can briefly re-show a just-deleted card | Warning | Self-corrects when the delete's own UPDATE event arrives in order or on resync; transient, narrow race. |
| `app/services/sessions.py` | 61-62, 231-233 | WR-03: reorder silently no-ops when float gap exhausted (~50 alternating interior swaps) | Warning | Edge case; no recovery or message. |
| `app/services/sessions.py` / `repository.py` | 224-239 / 164-168 | WR-04: reorder write not conditional on quadrant | Warning | Concurrent move+reorder race can land the card at an odd position; no data corruption. |
| `app/ui/canvas_view.py` | 390-410 | WR-05: `_write` tail not guarded by `_gone()` | Warning | Closed-tab-mid-write edge; possible logged exception. |
| (review INFO) | - | IN-01..IN-04 | Info | Unused dataclass fields, server-clock `deleted_at`, duplicated test helpers, fixed sleeps. |

None of the five warnings contradicts a ROADMAP success criterion or a plan must-have truth as written (the failed-save truth requires rollback, message and editability, all met). They are recommended for triage before shipping; they are not gaps.

### Human Verification Required

See the `human_verification` list in the frontmatter (6 items): the five plan-deferred real-browser checks (inline edit feel/latency, no-refocus + Shift+Enter + blur/Esc, cross-window draft protection, Move to submenu hover/tap and instant delete/move, greyed Move up/down at the edges) and the `backstop` concurrent-writer truth.

### Gaps Summary

No gaps. Every ROADMAP success criterion is backed by code that exists, is substantive, is wired, and is exercised by passing offline and hosted tests (283 offline, 13 hosted verified by the verifier in this run; migration confirmed applied on the remote). The phase cannot be marked `passed` only because real-browser interaction checks and the non-inferable concurrent-writer truth need a human. Open review warnings WR-01..WR-05 should be triaged (fix or defer) by the developer.

---

_Verified: 2026-10-23T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
