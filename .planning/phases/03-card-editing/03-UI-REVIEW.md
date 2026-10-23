# Phase 03 (card-editing) UI Review

**Audited:** 2026-10-23
**Baseline:** Abstract 6-pillar standards (no 03-UI-SPEC.md exists; UI safety gate overridden for this phase by user). 03-01..03-05 SUMMARYs and CONTEXT D-01..D-10 used as the behavioral contract.
**Screenshots:** not captured (no dev server running; code-only audit)
**Interaction captures:** off (`interaction_capture: false`)
**Overall:** 16/24

## Pillar Scores

| Pillar | Score | Key Finding |
|---|---|---|
| 1. Copywriting | 3/4 | Specific messages, but a failed delete shows "Card deleted" then "Could not delete the card" |
| 2. Visuals | 3/4 | Click-to-edit text has no affordance beyond cursor-pointer; crowded meta row |
| 3. Color | 2/4 | `text-grey` (#9E9E9E, ~2.7:1) still on "No cards yet" (canvas_view.py:142) — carried from 02-UI-REVIEW |
| 4. Typography | 3/4 | Five text styles at the page level; no weight hierarchy inside a card |
| 5. Spacing | 3/4 | Quasar utilities only; meta row `no-wrap` with unbounded author label can push the more_vert button off a 375px card |
| 6. Experience Design | 2/4 | Strong state handling, but card text not keyboard-reachable, invalid-blur trap has no exit hint, no in-flight cue, duplicate "Add" names remain |

No pillar scored 1 and no defect blocks a core task: all findings are WARNINGs.

## Top 3 Priority Fixes

1. **Failed delete shows two contradictory toasts.** `_delete_card` (canvas_view.py:426) notifies `CARD_DELETED` before the write; on failure `_write` adds `DELETE_FAILED` (line 399). Fix: keep the notification handle and dismiss it on failure, or notify `CARD_DELETED` only after `_write` succeeds.
2. **Editor exit is undiscoverable; invalid blur traps the user.** With empty/over-length text, blur keeps the editor open (D-03) and only Esc exits, which the UI never says. Fix: a caption under the textarea in `_start_edit` ("Enter saves · Shift+Enter new line · Esc cancels"), also shown in the error state. Keep the D-03 behavior.
3. **Contrast and overflow on the card meta row.** canvas_view.py:142 `text-grey` → `text-grey-8` (same fix as line 252; canvas_page.py:62 has the same class). Line 250: add truncation (`ellipsis`, `min-width: 0` or a max-width) so long author names cannot push the more_vert button (line 258) off narrow cards.

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- WARNING: Failed delete shows "Card deleted" then "Could not delete the card. Please try again." (canvas_view.py:426, :399) — contradictory feedback.
- WARNING (carried from Phase 2): four "Add" buttons (canvas_view.py:150) with identical "New card" fields (line 147); quadrant-specific names proposed in Phase 2 not applied.
- OK: EDIT_FAILED, CARD_GONE, MOVE_FAILED, DELETE_FAILED, CARD_TEXT_ERROR are specific and follow the "Could not … Please try again." pattern. Menu items Edit / Move to / Move up / Move down / Delete match D-07.

### Pillar 2: Visuals (3/4)
- WARNING: Click-to-edit has no visual affordance (canvas_view.py:243-247 label with `cursor-pointer` only).
- WARNING: Meta line plus a 40px more_vert button per card is heavy relative to content; Phase 2 quadrant hierarchy (no tint/icon) still unaddressed.
- OK: "(edited)" marker is text, not color alone (D-06).

### Pillar 3: Color (2/4)
- WARNING (carried): "No cards yet" (canvas_view.py:142) uses `text-grey` at ~2.7:1, below WCAG AA; only the meta line (252) was fixed.
- WARNING (carried): four identical primary "Add" buttons visible at once; no 60/30/10 accent split.
- OK: No hex/rgb literals under app/ui; color is never the sole signal for edited/disabled/error states.

### Pillar 4: Typography (3/4)
- WARNING: text-h6 (quadrant titles, line 137), text-caption (meta, 252), default body (card text), plus h4/h5 elsewhere in app/ui — five styles, at the limit.
- WARNING (carried): card text at default body with a 0.75rem meta line limits reading density.
- OK: Textarea inherits Quasar default size, matching card text.

### Pillar 5: Spacing (3/4)
- OK: Standard Quasar utilities only (gap-2, gap-4, p-, m-, space-); no arbitrary px/rem.
- WARNING: Meta row (line 249) `justify-between w-full no-wrap` with unbounded author label + tooltip can push more_vert (line 258) past the card edge at 375px.
- WARNING (carried): quadrant column has no max-height or scroll region.

### Pillar 6: Experience Design (2/4)
- WARNING (keyboard): card text is a label with a click listener (line 248), no tabindex/role/keydown; keyboard users reach Edit only through the menu button.
- WARNING (discoverability/trap): D-03 keeps the editor open on invalid blur with no hint that Esc exits; no save/cancel hint anywhere.
- WARNING (in-flight cue): during a write `_start_edit` returns silently (line 494); only cue is the disabled menu button. Accepted by a 03-01 decision but weakens "feel instant" on slow networks.
- WARNING (a11y, carried): duplicate Add button/field names.
- OK: Busy guard before first await, rollback to latest server row, CardGone removes card with warning, D-04 draft protection across remote edit/resync/move, D-10 disabled edge items. No-confirm delete is decision D-08 (accepted, not a finding).

## Recommendation Count

- Priority fixes: 3
- Minor recommendations: 6 (Add-button naming, quadrant max-height, quadrant tint, in-flight cue, keyboard path to card text, delete-toast wording)

## Files Audited

- .planning/phases/03-card-editing/03-01..03-05 SUMMARY.md and PLAN.md, 03-CONTEXT.md
- app/ui/canvas_view.py (read in full for card, menu, editor, write and resync paths)
- app/ui/canvas_page.py, app/ui/home_page.py, app/ui/identity.py (grep for copy and text-grey)
- .planning/phases/02-live-shared-canvas/02-UI-REVIEW.md (carried-over warnings)

*Auditor: gsd-ui-auditor (report returned inline; persisted by the orchestrator).*
