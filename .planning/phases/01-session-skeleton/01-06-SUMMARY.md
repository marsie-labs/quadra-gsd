---
phase: 01-session-skeleton
plan: 06
subsystem: ui
tags: [nicegui, identity, display-name, app.storage.user, supabase-check-constraint, tdd]

requires:
  - phase: 01-session-skeleton
    provides: "canvas page and UI harness (01-02), fake services and UI tests (01-03), create_app with 1-year session cookie (01-05)"
provides:
  - "app/ui/identity.py: validate_display_name, current_name, save_display_name, name_banner, ensure_display_name"
  - "Canvas header with read-only display-name label and inline name banner when unnamed"
  - "Reusable ensure_display_name() authoring gate for Phase 2 (returns None on cancel, never a placeholder)"
  - "Two-browser no-login canvas test (SESS-04)"
  - "DB-level cards.author CHECK parity test (D-02 groundwork for Phase 2 IDEN-03)"
affects: [02-cards, phase-2-iden-03]

actuals:
  tokens: 5800
  tasks: 2
  commits: 4
plan_head_before: 2463ab129c5a0504efb8264e39eb5b9f0d7b85eb
plan_head_after: a256e09f7f74f4cc0687566dea36606698eb5d4f
commits: 4

tech-stack:
  added: []
  patterns:
    - "Identity helpers take an injectable storage mapping (defaults to app.storage.user) so rules are unit-testable without a NiceGUI context"
    - "Authoring gate: await ensure_display_name(); a None result means abort the action"
    - "Test-only pages live in tests/ui/ui_main.py, never under app/"

key-files:
  created:
    - app/ui/identity.py
    - tests/unit/test_identity.py
    - tests/ui/test_identity.py
    - tests/ui/test_canvas.py
    - tests/ui/test_ensure_name.py
    - tests/integration/test_card_author_check.py
  modified:
    - app/ui/canvas_page.py
    - tests/ui/ui_main.py

key-decisions:
  - "save_display_name returns the already-stored name instead of overwriting, so a stale banner or dialog in a second tab cannot rename the browser (D-03)"
  - "Display name length counts Python code points after trim, matching Postgres char_length on cards.author"
  - "Invalid stored values are ignored by current_name (treated as no name) rather than trusted"

patterns-established:
  - "Inline non-modal banner for first-visit name capture; canvas renders fully behind it (D-01)"
  - "User-controlled text renders only through ui.label (no ui.html/ui.markdown under app/ui)"

requirements-completed: [SESS-04, IDEN-01, IDEN-02]

coverage:
  - id: D1
    description: "A second browser with fresh cookies and no login opens the same /s/{session_id} and sees the same project name and four quadrants, with no login prompt"
    requirement: SESS-04
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_canvas.py#test_second_browser_opens_same_session_without_login"
        status: pass
    human_judgment: false
  - id: D2
    description: "First-time visitors see an inline, non-blocking name banner above a fully visible canvas; invalid names show the inline error and store nothing"
    requirement: IDEN-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_identity.py#test_first_visit_shows_banner_over_a_fully_visible_canvas"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_identity.py#test_invalid_name_shows_inline_error_and_keeps_banner"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity.py#test_validate_display_name"
        status: pass
    human_judgment: false
  - id: D3
    description: "Saved name is shown read-only in the header and survives reload and other sessions, including 'Zoe with diaeresis + emoji' exactly as saved"
    requirement: IDEN-02
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_identity.py#test_name_persists_across_reload_and_other_sessions"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_identity.py#test_unicode_name_round_trips_exactly"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_identity.py#test_header_name_is_read_only_text"
        status: pass
    human_judgment: false
  - id: D4
    description: "ensure_display_name() returns the stored name with no dialog, prompts otherwise, and returns None on Cancel"
    requirement: IDEN-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_ensure_name.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Database rejects an empty or 41-character card author and accepts 40 multi-byte characters"
    requirement: IDEN-01
    verification:
      - kind: integration
        ref: "tests/integration/test_card_author_check.py#test_db_enforces_author_length_like_validate_display_name"
        status: pass
    human_judgment: false
  - id: D6
    description: "End-of-phase walkthrough: create a session, banner and read-only name look and feel right in two real browsers"
    verification: []
    human_judgment: true
    rationale: "Real-browser look and feel and the private-window no-login experience are not asserted by the simulated-browser tests; items 5 and 6 of the walkthrough were smoke-checked automatically"

duration: 2min
completed: 2026-10-22
status: complete
---

# Phase 1 Plan 6: Participant Identity Summary

**Inline per-browser display-name banner with read-only header name, a reusable `ensure_display_name()` authoring gate for Phase 2, and a two-browser no-login canvas test, backed by a DB author-constraint parity test.**

## Performance

- **Duration:** 2 min (wall clock)
- **Started:** 2026-10-22T22:08:24Z
- **Completed:** 2026-10-22T22:10:42Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 8 (6 created, 2 modified)

## Accomplishments
- Unnamed visitors see an ignorable inline banner above a fully visible four-quadrant canvas; no modal, no join screen (D-01).
- Names are trimmed, 1-40 code points, duplicates allowed (D-04), stored once per browser in signed `app.storage.user` and shown read-only in the header (D-03). They persist across reloads and sessions (IDEN-02).
- `ensure_display_name()` returns the stored name immediately, otherwise prompts in a dialog, and returns None on Cancel so the caller aborts. It never invents a placeholder (D-02).
- SESS-04: a second browser with fresh cookies opens the same link and sees the same project and quadrants with no login prompt.
- The hosted database independently rejects empty and 41-character authors and accepts 40 x 'é' (verified live).

## Task Commits

Both tasks followed RED then GREEN (no refactor commits needed):

1. **Task 1: banner, memory, read-only header, two-browser canvas test**
   - RED `8aa00f0` (test)
   - GREEN `1ee3f2d` (feat)
2. **Task 2: ensure_display_name gate and DB author parity**
   - RED `8ed1be0` (test)
   - GREEN `a256e09` (feat)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Gate Compliance

`workflow.tdd_mode` is not enabled in `.planning/config.json`, so the classifier verb was not required. RED/GREEN were still done by hand:

- **Task 1 RED:** the 11 UI identity tests failed on their planned assertions (banner / display-name marker not found on the canvas). `tests/unit/test_identity.py` failed at import (`ModuleNotFoundError: app.ui.identity`), which is a load failure rather than a strict assertion failure; the UI tests carry the assertion-level RED evidence. `test_second_browser_opens_same_session_without_login` was green at RED by design: SESS-04 already held from 01-02 and the test guards it against this plan's header and banner edits.
- **Task 2 RED:** the 4 `ensure_display_name` UI tests failed because `/_test/author-action` did not exist yet (404). `test_card_author_check.py` passed at RED by design: the CHECK was already in the 01-02 migration, so it is a parity characterization test.
- GREEN commits follow the RED commits for both tasks.
- Minor process slip: the Task 1 RED commit contained two ruff findings in the new unit test file (one line over 100 columns and unsorted imports). The GREEN commit fixed them; nothing was amended.

## Files Created/Modified
- `app/ui/identity.py` - validate/current/save helpers, `name_banner`, `ensure_display_name`
- `app/ui/canvas_page.py` - read-only `display-name` label in the header and banner when unnamed
- `tests/unit/test_identity.py` - validation and storage rules, no NiceGUI context
- `tests/ui/test_identity.py` - banner, errors, persistence, read-only header, second browser
- `tests/ui/test_canvas.py` - SESS-04 two-browser no-login test
- `tests/ui/test_ensure_name.py` - the D-02 gate
- `tests/ui/ui_main.py` - test-only `/_test/author-action` page
- `tests/integration/test_card_author_check.py` - live DB author CHECK parity

## Decisions Made
- `save_display_name` is a no-op returning the existing name when a valid one is stored (D-03), so stale tabs cannot rename.
- `current_name` ignores invalid stored values rather than trusting them.
- `ensure_display_name` returns `result or None`, so any falsy dialog result aborts the caller's action.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `ruff format` reflowed an inline comment in `canvas_page.py` into an awkward position; moved the comment above the call and re-ran ruff. No behavior impact.

## Verification Results
- `uv run pytest -q`: 90 passed (13 integration deselected).
- Full phase gate `uv run pytest -q -m "integration or not integration" -rs`: **103 passed, 0 skipped, 0 failed** against hosted Supabase.
- `uv run ruff check .` and `uv run ruff format --check .`: clean.
- Grep gates: no `Anonymous` and no `ui.html`/`ui.markdown` under `app/`; `/_test/author-action` absent from `app/`.
- Human walkthrough (end-of-phase, `human_verify_mode=end-of-phase`): items 1-4 (browser flows) are covered by the simulated-browser tests but remain for the verifier's human check. Items 5 and 6 were smoke-checked against a real `uv run python -m app`: `/s/doesnotexist` returns 404 with "Session not found", and `/healthz` reports realtime `verified`. The test-only page returns 404 on the real app.

## Known Stubs

None. (The header name is intentionally empty when no name is stored, per the plan; this is not a stub.)

## Threat Flags

None. No new endpoints, auth paths or schema changes. T-01-20 (stored XSS) is mitigated by ui.label-only rendering, enforced by the grep gate; T-01-22 by the None-on-cancel contract plus the live DB CHECK test.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 2 can call `await ensure_display_name(on_saved=on_name_saved)` before any card write and abort on None. The `on_name_saved` closure already exists in the canvas page.
- IDEN-03 (author recorded on cards) is Phase 2's, per the revision-2 remap.
- This is the last plan of Phase 1; the phase is ready for verification and the end-of-phase human walkthrough.

---
*Phase: 01-session-skeleton*
*Completed: 2026-10-22*
