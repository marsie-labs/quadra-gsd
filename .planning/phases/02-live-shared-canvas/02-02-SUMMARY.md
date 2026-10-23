---
phase: 02-live-shared-canvas
plan: 02
subsystem: card-authoring
tags: [nicegui, supabase, postgres-check, pydantic, pytest, tdd]

requires:
  - phase: 02-live-shared-canvas
    provides: "02-01 tracer: add_card, list_cards, CanvasView, apply_card, FakeRepository card helpers"
  - phase: 01-session-skeleton
    provides: "ensure_display_name gate, name banner, cards/workspaces CHECKs, init migration"
provides:
  - "Migration 20261023000000_author_nonblank (cards_author_nonblank, workspaces_closed_by_nonblank), pushed to the hosted project"
  - "validate_card_text, MAX_CARD_TEXT, CARD_TEXT_ERROR, MAX_AUTHOR, InvalidCardText, InvalidCardAuthor; add_card validates before any write and stores trimmed text and author"
  - "Add handler with inline text error, validate-before-name-gate, per-quadrant re-entrancy flag, failure notify that keeps the text"
  - "Banner and dialog handlers idempotent (WR-06); naming through the add dialog removes the inline banner"
  - "Live CARD-07 storage, ordering and DB text-boundary proofs"
affects: [02-03-live-fidelity, 02-04-reconnect-recovery, 02-05-realtime-recovery]

actuals:
  tokens: 7574
  tasks: 3
  commits: 5

plan_head_before: 5dbbecf2831b1679bd76470fed892be77c08b061
plan_head_after: d601ddbc15988da046204cdca3b229dbf9cc8bfd
commits: 5

tech-stack:
  added: []
  patterns:
    - "Per-quadrant in-flight set (CanvasView._adding): added before the first await, discarded in finally, button disabled meanwhile"
    - "Validate text before the name gate so invalid input never opens the dialog"
    - "Idempotent element deletion: guard with is_deleted when a handler can run twice on stale references"

key-files:
  created:
    - supabase/migrations/20261023000000_author_nonblank.sql
    - tests/integration/test_card_storage.py
    - tests/unit/test_card_rules.py
    - tests/ui/test_card_authoring.py
  modified:
    - tests/integration/test_card_author_check.py
    - app/services/sessions.py
    - app/ui/canvas_view.py
    - app/ui/canvas_page.py
    - app/ui/identity.py
    - tests/ui/fakes.py
    - tests/ui/test_cards.py

key-decisions:
  - "Card text is trimmed with str.strip() then counted in code points (1-500), matching Postgres char_length on the stored trimmed text; the service stores the trimmed text and trimmed author"
  - "No browser-side length limit or counter on the add field: it counts UTF-16 units and would block valid 500-code-point emoji text; the server rule is the authority"
  - "Text is validated before the name gate, so invalid text never opens the name dialog"
  - "The banner reference lives in canvas_page; on_name_saved removes it if still present, so the dialog path and the banner path converge on one header update"

patterns-established:
  - "FakeRepository gates and failure injection (insert_gate, fail_next_insert_codes) mirror create_gate and fail_next_create_codes"
  - "Reproduce queued duplicate events in tests by calling a captured listener handler twice (trigger() finds no listeners after the element is deleted)"

requirements-completed: [CARD-01, CARD-06, CARD-07, IDEN-03]

coverage:
  - id: D1
    description: "Database rejects space-only card authors and workspaces.closed_by from any writer (migration pushed to the hosted project; closes WR-07 / security R4)"
    requirement: IDEN-03
    verification:
      - kind: integration
        ref: "tests/integration/test_card_author_check.py (uv run pytest -m integration)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A card stored through SessionService carries quadrant, session, author, order_index 1024-gapped, matching timestamps and null deleted_at; ties sort by created_at then id; soft-deleted rows are excluded; DB text boundaries hold (500 x e-acute accepted, 501 and blank rejected)"
    requirement: CARD-07
    verification:
      - kind: integration
        ref: "tests/integration/test_card_storage.py (3 tests, live Supabase)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Empty, whitespace-only and over-500-code-point card text is rejected with 'Card text is required (max 500 characters)' on that quadrant's field and writes nothing; 500 code points (multi-byte too) are stored trimmed"
    requirement: CARD-01
    verification:
      - kind: unit
        ref: "tests/unit/test_card_rules.py"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_cards.py#test_blank_text_shows_inline_error_and_writes_nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "Card text and author render literally ('<b>x</b>', 'Zoe with emoji') via ui.label"
    requirement: CARD-06
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_cards.py#test_card_text_and_author_render_literally"
        status: pass
    human_judgment: false
  - id: D5
    description: "An unnamed participant adding a card is asked for a name; Cancel writes nothing and keeps the text and banner; Continue authors the card with that name, updates the header and removes the banner; no placeholder author exists"
    requirement: IDEN-03
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_card_authoring.py#test_unnamed_add_cancel_writes_nothing"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_card_authoring.py#test_unnamed_add_continue_authors_card"
        status: pass
    human_judgment: false
  - id: D6
    description: "Rapid double submit creates one card; a failed write keeps the text and frees the field; repeated banner submits are harmless (WR-06)"
    requirement: IDEN-03
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_card_authoring.py (double submit, failed write, banner double enter)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Two tabs of one browser saving different names at the same time: the card author is the value save_display_name returns, not the dialog's raw input (backstop truth; the user fixture cannot simulate two tabs of one browser)"
    requirement: IDEN-03
    verification: []
    human_judgment: true
    rationale: "Not simulable with the NiceGUI user fixture (each simulated user is a separate browser); save_display_name returning the stored name is unit-tested in Phase 1"
  - id: D8
    description: "Look and feel of the add flow in a real browser: name dialog, 'name - HH:MM' in server local time with the full timestamp on hover, inline error under the right field, double click yields one card"
    verification: []
    human_judgment: true
    rationale: "Plan marks this as an end-of-phase human check; visual adequacy and real browser event timing are not asserted by tests"

duration: 33min
completed: 2026-10-23
status: complete
---

# Phase 2 Plan 02: Card Authoring Edges Summary

**Space-only authors are now refused by the hosted database (migration pushed), card text is validated 1-500 code points with an inline per-quadrant error, and adds are single-shot with the name gate at add time.**

## Performance

- **Duration:** 33 min wall clock, including the schema-push checkpoint wait
- **Started:** 2026-10-23T10:43:45Z
- **Completed:** 2026-10-23T11:16:34Z (before the metadata commit)
- **Tasks:** 3
- **Files modified:** 11 (4 created, 7 modified)

## Accomplishments

- Hosted Supabase rejects `cards.author = '   '` and `workspaces.closed_by = '   '` with SQLSTATE 23514 from any writer, closing Phase 1 review WR-07 / security R4. The pushed init migration is untouched.
- The stored card shape (CARD-07) is proven live: quadrant, workspace, author, `order_index` 1024 then 2048, equal `created_at`/`updated_at`, null `deleted_at`; ties sort by `created_at` then `id`; soft-deleted rows are excluded; the DB text boundary holds at 500 code points.
- `validate_card_text` mirrors `validate_project_name`; `add_card` rejects bad text or author before any repository call and stores trimmed values.
- The add handler shows "Card text is required (max 500 characters)" on that quadrant's field only, before the name gate, and clears it on typing and after a successful add.
- Unnamed participants are asked "Enter your name to continue" when adding; Cancel writes nothing and keeps the text; Continue authors the card, sets the header and removes the inline banner.
- A per-quadrant in-flight flag makes double click / double Enter create exactly one card; failures show "Could not add the card. Please try again.", keep the text and release the quadrant.

## Schema-push evidence (Task 1, blocking)

- Precondition met. Pre-push `supabase migration list --linked --agent no` showed only `20261022000000` on Local and Remote.
- Dry run, `supabase db push --linked --dry-run`: "Would push these migrations: • 20261023000000_author_nonblank.sql".
- Push command run: `supabase db push --linked --yes`. **It was run by the human in their own shell**, because the Claude Code auto-mode classifier denied it for the executor (same outcome as Phase 1). The push output was not captured; the migration-list rows below are the evidence.
- Confirmation, `supabase migration list --linked --agent no`:

```
   Local            | Remote           | Time (UTC)
  ------------------|------------------|-----------------------
   `20261022000000` | `20261022000000` | `2026-10-22 00:00:00`
   `20261023000000` | `20261023000000` | `2026-10-23 00:00:00`
```

- Re-checked by this continuation agent: `supabase migration list --linked --agent no | grep -E '20261023000000.? +\| +.?20261023000000'` matches the row `20261023000000 | 20261023000000 | 2026-10-23 00:00:00`.
- `git diff --quiet HEAD -- supabase/migrations/20261022000000_init_schema.sql` exits 0.

## RED / GREEN evidence

**Task 1 (live tests against Remote).** Before the push, `uv run pytest -m integration tests/integration/test_card_author_check.py tests/integration/test_card_storage.py -q -rs` gave 2 failed, 3 passed. The two failures were the space-only cases (`test_db_enforces_author_length_like_validate_display_name` with the `"   "` author, and `test_db_rejects_space_only_closed_by`): `DID NOT RAISE APIError`. The three storage tests exercise the existing schema and passed. After the push: 5 passed, 0 skipped. The `"   "` author case was folded into the existing author test, so test_card_author_check.py has 2 tests (5 in total).

**Task 2 (RED commit 46ebf29, GREEN 3366679).** 23 failed, 10 passed before implementation:
- `tests/unit/test_card_rules.py`: all `validate_card_text` cases and `test_card_rule_constants` failed with ImportError (symbols absent); the five `add_card` tests failed on the missing `InvalidCardText` / `InvalidCardAuthor` imports.
- `tests/ui/test_cards.py`: both blank-text cases, `test_oversized_text_shows_inline_error_and_writes_nothing`, `test_unnamed_invalid_text_never_opens_the_name_dialog` and `test_error_clears_on_typing_and_after_a_successful_add` failed with "expected to see ... Card text is required (max 500 characters)" (the 02-01 handler logged `add_card failed: APIError` instead).
- Already green by design (behavior from 02-01 or pure helpers): `next_order_index`, the time-format test, `test_500_code_points_are_stored_and_shown`, `test_card_text_and_author_render_literally`.
- Semantic assessment: every RED failure was the planned missing behavior (absent symbol or missing inline error), not a fixture, syntax or collection fault.

**Task 3 (RED commit ebfcc22, GREEN d601ddb).** 3 failed, 2 passed before implementation:
- `test_unnamed_add_continue_authors_card`: `name-banner` still on the page after the dialog saved the name.
- `test_double_submit_creates_one_card`: `insert_calls == 3`, expected 1.
- `test_banner_double_enter_is_harmless`: `ValueError: list.remove(x): x not in list` from the second `banner.delete()` (WR-06).
- Already green by design: `test_unnamed_add_cancel_writes_nothing` and `test_failed_write_keeps_text_and_releases` (02-01 already gated on `ensure_display_name` and notified on failure).
- Semantic assessment: each failing test failed on the planned assertion for the intended reason.

## Task Commits

1. **Task 1: author_nonblank migration and live storage proofs** - `7b4c316` (feat)
2. **Task 2 RED: failing tests for card text and author rules** - `46ebf29` (test)
3. **Task 2 GREEN: reject empty or oversized card text** - `3366679` (feat)
4. **Task 3 RED: failing tests for the name gate and double submit** - `ebfcc22` (test)
5. **Task 3 GREEN: name gate at add time, single-shot adds, WR-06** - `d601ddb` (feat)

**Plan metadata:** recorded in the docs(02-02) commit that adds this file.

## Files Created/Modified

- `supabase/migrations/20261023000000_author_nonblank.sql` - two additive btrim CHECKs and a PostgREST schema reload
- `app/services/sessions.py` - card text/author constants, exceptions, `validate_card_text`, validating `add_card`
- `app/ui/canvas_view.py` - add handler: inline error, name gate, per-quadrant flag, disabled button, failure notify
- `app/ui/canvas_page.py` - banner reference; `on_name_saved` also removes the banner if it still exists
- `app/ui/identity.py` - banner and dialog deletion guarded by `is_deleted` (WR-06)
- `tests/integration/test_card_author_check.py`, `tests/integration/test_card_storage.py` - live DB proofs
- `tests/unit/test_card_rules.py`, `tests/ui/test_card_authoring.py`, `tests/ui/test_cards.py`, `tests/ui/fakes.py` - rule, authoring and fake-repository support

## Decisions Made

See `key-decisions` in the frontmatter. In short: trim then count code points; no browser-side length limit; validate before the name gate; one `on_name_saved` converges the banner and dialog paths.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test fidelity] Banner double-Enter test calls a captured handler twice**
- **Found during:** Task 3 RED
- **Issue:** Planned as "trigger keydown.enter twice", but nicegui's `_handle_delete` clears an element's event listeners, so the second `trigger()` is a no-op and the test passed before the WR-06 fix, so it could not prove the fix.
- **Fix:** The test captures the listener's handler before the first call and invokes it twice with the user client active, reproducing two events queued against the same banner. It then failed with `ValueError: list.remove(x): x not in list` and passes after the fix.
- **Files modified:** tests/ui/test_card_authoring.py
- **Committed in:** ebfcc22

**2. [Rule 3 - Blocking] The permission system denied `supabase db push` for the executor**
- Handled through the plan's own authentication-gate path (checkpoint:human-action); the human ran the push. Documented under Schema-push evidence, not a plan deviation.

**3. [Rule 1 - Test design] Name field in the dialog found by ancestry**
- The banner and the dialog both label their field "Your name", so `user.find("Your name")` matches two inputs. `_dialog_name_input` in tests/ui/test_card_authoring.py selects the one inside a `ui.dialog`.

---

**Total deviations:** 2 auto-fixed test-side adjustments (Rules 1 and 3 in spirit), 0 production-code deviations.
**Impact on plan:** None on scope; both adjustments make the planned tests actually prove their claims.

## Issues Encountered

- The plan's Task 3 acceptance criterion expects the banner double Enter to be RED; the literal `trigger` approach was green already (see deviation 1). Resolved as described.
- Pre-existing note: `FakeRepository.insert_card` mirrors the DB with a `strip(" ")` text check and `len(author) <= 40`; the service now guarantees trimmed values before that point.

## Known Stubs

None.

## Threat Flags

None. No new network endpoints, auth paths or trust-boundary schema changes beyond the planned CHECK constraints (threat register T-02-07 to T-02-12 mitigations implemented: T-02-07 validate_card_text plus live text-boundary test; T-02-08 migration plus InvalidCardAuthor; T-02-09 in-flight flag test; T-02-11 dry-run and migration-list evidence; T-02-12 gate abort test and the Anonymous grep guard).

## User Setup Required

None - no external service configuration required beyond the already-completed schema push.

## Next Phase Readiness

- 02-03 can build on validated, trimmed, single-shot card writes and the live-proven stored shape.
- Human end-of-phase check still pending (D8): run `uv run python -m app`, add a card as an unnamed participant, try empty and 501-character text, double-click Add.
- Full suite at the end of this plan: 134 passed (18 integration deselected by default), `ruff check` and `ruff format --check` clean.

## Self-Check: PASSED

- Files found: supabase/migrations/20261023000000_author_nonblank.sql, tests/integration/test_card_storage.py, tests/unit/test_card_rules.py, tests/ui/test_card_authoring.py, app/services/sessions.py, app/ui/canvas_view.py, app/ui/canvas_page.py, app/ui/identity.py, tests/ui/fakes.py, tests/ui/test_cards.py, tests/integration/test_card_author_check.py
- Commits present on HEAD: 7b4c316, 46ebf29, 3366679, ebfcc22, d601ddb
- Acceptance greps: `cards_author_nonblank`, `workspaces_closed_by_nonblank`, `notify pgrst, 'reload schema';` in the migration; `def validate_card_text(`, `class InvalidCardText`, `class InvalidCardAuthor` in sessions.py; `CARD_TEXT_ERROR` and `validate_card_text(` in canvas_view.py; no `maxlength` in canvas_view.py; `is_deleted` twice in identity.py; `banner = name_banner(` in canvas_page.py; no `Anonymous` under app/; no `ui.html`/`ui.markdown` under app/ui.

---
*Phase: 02-live-shared-canvas*
*Completed: 2026-10-23*
