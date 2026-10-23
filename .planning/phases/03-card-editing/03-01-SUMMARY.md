---
phase: 03-card-editing
plan: 01
subsystem: ui
tags: [nicegui, supabase, postgres-trigger, realtime, inline-edit, optimistic-ui]

requires:
  - phase: 02-live-shared-canvas
    provides: CanvasView projection, RealtimeHub fan-out (UPDATE -> apply_card), stale guard, two-browser live test pattern
provides:
  - cards.text_updated_at column and cards_touch BEFORE UPDATE trigger (migration 20261023120000, pushed to hosted project)
  - CardView.text_updated_at, Repository.update_card_text, CardGone, SessionService.edit_card
  - In-place CanvasView projection with optimistic overlay (_optimistic), guarded write path (_write) and inline editor
  - card_meta_text with "(edited)" marker (D-06)
  - Live two-browser edit tracer test
affects: [03-02, 03-03, 03-04, 03-05, phase-05-agent-snapshot]

actuals:
  tokens: 6000
  tasks: 2
  commits: 2

plan_head_before: 4bb8c2f686aa066577040caaad05ef2e258576c3
plan_head_after: 15cda2b7fe135594b3b346c98902f30906015600

tech-stack:
  added: []
  patterns:
    - "DB trigger owns updated_at / text_updated_at; writers send only text"
    - "CanvasView keeps latest server row per card plus one optimistic overlay per in-flight write; _render updates widgets in place"
    - "One guarded write path (_write) for all card actions: busy guard before first await, rollback to latest server row on failure"

key-files:
  created:
    - supabase/migrations/20261023120000_card_edit_tracking.sql
    - tests/integration/test_live_card_edits.py
  modified:
    - app/models.py
    - app/db/repository.py
    - app/services/sessions.py
    - app/ui/canvas_view.py
    - README.md

key-decisions:
  - "updated_at is maintained by the cards_touch trigger: greatest(clock_timestamp(), old.updated_at + 1 microsecond), so it strictly increases per row and the Phase 2 stale guard stays sound"
  - "text_updated_at is nullable (null = never edited, no backfill); the trigger sets it only when text changes, so writers cannot forge or clear it"
  - "edit_card writes only text via PostgREST update scoped by id, workspace_id and deleted_at is null; no RPC; an empty result raises CardGone"
  - "Optimistic row lives in a separate _optimistic overlay, not in _cards, so the stale guard and echoes never compete with an unconfirmed row"

requirements-completed: [CARD-02, CARD-08]

coverage:
  - id: D1
    description: "Editing a card inline in browser A is stored in hosted Supabase and shows live with '(edited)' in browser B within about 1 s"
    requirement: CARD-02
    verification:
      - kind: integration
        ref: "tests/integration/test_live_card_edits.py#test_card_edited_in_one_browser_shows_live_in_another"
        status: pass
    human_judgment: false
  - id: D2
    description: "The edited card is updated in place in the acting browser: exactly one card-{id} element after confirmation and echo"
    requirement: CARD-08
    verification:
      - kind: integration
        ref: "tests/integration/test_live_card_edits.py#test_card_edited_in_one_browser_shows_live_in_another"
        status: pass
    human_judgment: false
  - id: D3
    description: "The cards_touch trigger stamps updated_at and text_updated_at; edit_card changes only text (author, quadrant_id, order_index, created_at unchanged)"
    requirement: CARD-02
    verification:
      - kind: integration
        ref: "tests/integration/test_live_card_edits.py#test_card_edited_in_one_browser_shows_live_in_another"
        status: pass
    human_judgment: false
  - id: D4
    description: "Migration 20261023120000 applied to the hosted project and documented in the README"
    verification:
      - kind: other
        ref: "supabase migration list --linked --agent no"
        status: pass
    human_judgment: false
  - id: D5
    description: "Inline editor feel (click text, textarea in the card, Enter saves, instant update in the acting browser)"
    requirement: CARD-02
    verification: []
    human_judgment: true
    rationale: "Plan marks the end-of-phase human check (uv run python -m app, two windows); visual and interaction feel is not asserted by any test"

duration: ~1 session plus one human checkpoint (not precisely measured)
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 1: Card Edit Tracer Summary

**Inline card editing end to end: click text, edit in place, Enter saves; a cards_touch trigger on hosted Supabase stamps updated_at/text_updated_at and other browsers show the new text with "(edited)" live (562 ms measured), with CanvasView now updating cards in place via an optimistic overlay.**

## Performance

- **Duration:** not precisely measured (two executor sessions with a human schema-push checkpoint between them)
- **Completed:** 2026-10-23
- **Tasks:** 2
- **Files modified:** 7 (376 insertions, 34 deletions outside .planning)

## Accomplishments
- Migration `20261023120000_card_edit_tracking.sql`: nullable `cards.text_updated_at`, `public.cards_touch()` (security invoker, `set search_path = ''`) and the `cards_touch` BEFORE UPDATE trigger; applied to the hosted project.
- `Repository.update_card_text` (scoped by id, workspace_id, `deleted_at is null`, sends only `text`) and `SessionService.edit_card` (validates, raises `CardGone` on an empty result).
- `CanvasView` reworked from delete-and-rebuild to in-place rendering: per-card widget bundle, `_optimistic` overlay, `_busy` guard, `_render`, the reusable `_write`, and the inline `card-editor` textarea saving on `keydown.enter.exact.prevent`. `card_meta_text` appends " (edited)" when `text_updated_at` is set.
- Live two-browser tracer test passes: **"LIVE: edit Enter -> browser B shows the edit: 562 ms"**; acting browser has exactly one `card-{id}` element; the hosted row shows `text_updated_at == updated_at > created_at` and unchanged author, quadrant_id, order_index, workspace_id and created_at.
- README migration table row, repair line and push-before-start sentence.

## Schema-push evidence (BLOCKING step)

Dry run, run by the first executor (`supabase db push --linked --dry-run`):

```
DRY RUN: migrations will *not* be pushed to the database.
Connecting to remote database...
Would push these migrations:
 • 20261023120000_card_edit_tracking.sql
{"upToDate":false,"dryRun":true,"migrations":["20261023120000_card_edit_tracking.sql"],"seeds":[],"roles":[],"message":"Finished supabase db push."}
```

Push: the executor's attempt `supabase db push --linked --yes` was denied by the permission system ("Blind Apply"), as in Phases 1 and 2. The **human** then ran `supabase db push --linked` in their own shell (authentication gate, checkpoint:human-action). Whether the CLI asked for a database password is not stated by the human.

Migration list, verified after the push (`supabase migration list --linked --agent no`, re-run by this executor and by the orchestrator):

```
   Local            | Remote           | Time (UTC)
  ------------------|------------------|-----------------------
   `20261022000000` | `20261022000000` | `2026-10-22 00:00:00`
   `20261023000000` | `20261023000000` | `2026-10-23 00:00:00`
   `20261023120000` | `20261023120000` | `2026-10-23 12:00:00`
```

No `migration repair` or alternate SQL route was used.

## Task Commits

1. **Task 1: Tracer (inline edit, in-place projection, edit-tracking migration)** - `c2db172` (feat)
2. **Task 2: README migration row, repair line, push-first note** - `15cda2b` (docs)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `supabase/migrations/20261023120000_card_edit_tracking.sql` - column, trigger function, trigger, schema reload notify
- `app/models.py` - `CardView.text_updated_at`
- `app/db/repository.py` - `CARD_COLUMNS` gains `text_updated_at`; `_update_live_card`, `update_card_text`
- `app/services/sessions.py` - `CardGone`, `edit_card`
- `app/ui/canvas_view.py` - in-place projection, optimistic overlay, `_write`, inline editor, `card_meta_text`, `EDIT_FAILED`, `CARD_GONE`
- `tests/integration/test_live_card_edits.py` - live two-browser edit tracer
- `README.md` - migration table row, repair line, push-first sentence

## Decisions Made
See `key-decisions` in the frontmatter; all follow the plan's "Design decisions recorded here" section.

## Deviations from Plan

### Process deviation

**1. [Process] Task 1 implementation committed before its live verification**
- **Found during:** Task 1
- **Issue:** The plan orders push, then live run, then commit. The first executor committed the implementation (`c2db172`) before the schema push because the push needs a human (authentication gate) and the executor could not continue past it in one run.
- **Fix:** After the human pushed, this continuation ran the live verify against the already-committed code. It passed first time, so no follow-up fix commit was needed and `c2db172` was not amended.
- **Verification:** `uv run pytest -m integration tests/integration/test_live_card_edits.py -q -rs` reported 1 passed, 0 skipped.

**Total deviations:** 1 process deviation, 0 auto-fixed code issues.
**Impact on plan:** None on the code; the tracer gate was satisfied by the live verify after the push, before any expansion (Task 2 is docs-only).

## Issues Encountered
- The executor's `supabase db push --linked --yes` was denied by the permission system, resolved by the human running the push (expected per the plan's authentication-gate instructions).

## Verification Results
- `supabase migration list --linked --agent no`: 20261023120000 on Local and Remote (grep gate matched).
- `uv run pytest -m integration tests/integration/test_live_card_edits.py -q -rs`: 1 passed, 0 skipped, 562 ms Enter to browser B.
- `uv run pytest -q`: 179 passed, 23 deselected (no edit to earlier test files). `ruff check` and `ruff format --check`: clean.
- Grep gates: no `ui.timer(`, no `ui.html`/`ui.markdown` under `app/ui`, no Settings/SecretStr references in `app/ui`: pass.
- Pushed migrations (`init_schema`, `author_nonblank`) unchanged per `git diff`.
- README acceptance: 3 greps non-zero, diff confined to the "Apply database migrations" section.
- Not run: the plan's `<human-check>` (run the app, two windows). Left for end-of-phase verification (coverage D5).

## Known Stubs
None.

## Threat Flags
None. Mitigations for T-03-01, T-03-02, T-03-03 and T-03-04 are proven by plan 03-02's tests as the threat model states; this plan implements the scoped update, the trigger and label-only text rendering.

## User Setup Required
None - no external service configuration beyond the migration push already done.

## Next Phase Readiness
- Plans 03-02 to 03-05 can reuse `_write`, `_optimistic`, `_render` and `edit_card`.
- Hosted DB now has the trigger, so 03-02's live trigger-rule tests can run.

## Self-Check: PASSED
- Files exist: migration, live test, `app/ui/canvas_view.py`, README (checked).
- Commits `c2db172` and `15cda2b` are ancestors of HEAD.
- Acceptance criteria for both tasks re-run and passing.

---
*Phase: 03-card-editing*
*Completed: 2026-10-23*
