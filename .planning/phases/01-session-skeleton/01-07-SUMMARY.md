---
phase: 01-session-skeleton
plan: 07
subsystem: ui
tags: [nicegui, idempotency, double-submit, gap-closure, pytest]

requires:
  - phase: 01-session-skeleton
    provides: "01-03 home page create flow and SessionService; 01-06 canvas landing"
provides:
  - "Home-page create() guarded by a per-page creating flag (set before first await, held after success, cleared on failure)"
  - "FakeRepository.create_gate to hold a create in flight"
  - "Six double-trigger and lock-lifecycle UI tests"
affects: [01-VERIFICATION re-verification, phase-1 human verification item 3]

actuals:
  tokens: 4000
  tasks: 2
  commits: 4

plan_head_before: 631ae51ecaef11e12f18e002ef0c61c7e25388e9
plan_head_after: 24fe389b996660edff9a8903ae7d5db3a08e782a
commits: 4

tech-stack:
  added: []
  patterns:
    - "Closure-local re-entrancy flag checked and set before the first await; success path returns without releasing"
    - "Gated fake repository (asyncio.Event) to hold a call in flight in NiceGUI user tests"

key-files:
  created: []
  modified:
    - app/ui/home_page.py
    - tests/ui/fakes.py
    - tests/ui/test_home.py

key-decisions:
  - "Lock is a closure local of home(): one lock per browser tab, never module-level"
  - "Success keeps the lock until navigation; every non-success outcome (APIError, InvalidProjectName) falls through to a single release step"
  - "No dedup by project name anywhere; service, repository and schema untouched"

requirements-completed: [SESS-01]

coverage:
  - id: D1
    description: "Double Enter while a create is in flight makes exactly one create_session call and one session; Create button reports disabled while held"
    requirement: SESS-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_double_enter_while_in_flight_creates_one_session"
        status: pass
    human_judgment: false
  - id: D2
    description: "Double click (two synchronous clicks) while in flight makes exactly one create_session call and one session"
    requirement: SESS-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_double_click_while_in_flight_creates_one_session"
        status: pass
    human_judgment: false
  - id: D3
    description: "After a successful create the form stays locked: Create stays disabled and a further Enter makes no create_session call"
    requirement: SESS-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_create_stays_locked_after_success_until_navigation"
        status: pass
    human_judgment: false
  - id: D4
    description: "01-03 backstop truth 'Create button disabled while a create is in flight, so a double-click produces exactly one session' (formerly code-inspection only) now has automated evidence"
    requirement: SESS-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_double_enter_while_in_flight_creates_one_session (button enabled False while held)"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_double_click_while_in_flight_creates_one_session (button enabled False while held)"
        status: pass
    human_judgment: false
  - id: D5
    description: "A failed create (APIError 42501) or a server-side InvalidProjectName rejection releases the lock and a retry lands on the canvas"
    requirement: SESS-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_failed_create_releases_the_lock_for_a_retry"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_rejected_name_releases_the_lock_for_a_retry"
        status: pass
    human_judgment: false
  - id: D6
    description: "Two browsers creating at once each make their own create_session call and get their own session (lock is per page instance)"
    requirement: SESS-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_home.py#test_two_browsers_creating_at_once_each_get_their_own_session"
        status: pass
    human_judgment: false
  - id: D7
    description: "Same project name twice still yields two distinct, openable sessions (no name dedup) - unit tier"
    requirement: SESS-01
    verification:
      - kind: unit
        ref: "tests/unit/test_sessions_service.py::test_same_name_twice_gives_two_distinct_openable_sessions"
        status: pass
    human_judgment: false
  - id: D8
    description: "Hosted-Supabase regression: create from home lands on canvas, and same-name-twice integration test (NOT RUN in this worktree - .env unavailable)"
    requirement: SESS-01
    verification:
      - kind: integration
        ref: "tests/integration/test_skeleton_e2e.py::test_create_from_home_lands_on_canvas"
        status: unknown
      - kind: integration
        ref: "tests/integration/test_create_session.py::test_same_name_twice_gives_two_sessions"
        status: unknown
    human_judgment: true
    rationale: "Hosted integration tests skipped because the gitignored .env could not be provisioned into the worktree (secret-read guard blocked the copy); orchestrator must run them from the main checkout"
  - id: D9
    description: "Real-browser double Enter and double click (VERIFICATION human item 3)"
    verification: []
    human_judgment: true
    rationale: "Real-browser confirmation stays an end-of-phase human check; the server-side flag now rejects the second event regardless of DOM state"

duration: 12min
completed: 2026-10-23
status: complete
---

# Phase 1 Plan 07: Home-page create single-shot guard Summary

**Per-page `creating` flag on the home form (checked and set before the first await, held after success, released on every failure) with gated-fake UI tests for double Enter, double click, lock lifecycle and two-browser independence; closes REVIEW WR-01.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-10-23T00:38Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `create()` in `app/ui/home_page.py` now returns immediately when `creating` is set, sets it before the single await, keeps it set after success (page stays locked until the browser navigates away), and clears it plus re-enables the button on every non-success outcome (generic exception or `InvalidProjectName`). The `finally` cleanup that re-enabled the button on success is gone.
- `FakeRepository.create_gate` (`asyncio.Event | None`) holds `create_session` in flight, enabling deterministic double-trigger tests.
- Six new tests in `tests/ui/test_home.py`; `test_home.py` is 11 passed, the quick suite is 96 passed.
- This plan closes REVIEW WR-01 and the single 01-VERIFICATION gap (01-03 truth "Create button disabled while in flight so a double-click produces one session"). VERIFICATION human item 3 (real-browser double Enter / double click) remains for the end-of-phase human check.

## RED / GREEN evidence

- **Task 1 RED** (commit `e5638f9`): both new tests failed on the in-flight assertion with `assert 2 == 1` (`create_calls`). Semantic assessment: the target tests executed, reached the planned assertion, and failed because `create()` had no re-entrancy flag.
- **Task 1 GREEN** (`7dd2c72`): named tests 2 passed; quick suite 92 passed; ruff check and format clean.
- **Task 2 RED** (`19c0ea3`): `test_create_stays_locked_after_success_until_navigation` failed on `assert not button.enabled` (`assert not True`: button re-enabled after success). The failed-create, rejected-name and two-browser tests passed on Task 1's code and stayed as guards.
- **Task 2 GREEN** (`24fe389`): `tests/ui/test_home.py` 11 passed (3 consecutive runs); quick suite 96 passed; ruff check and format clean.

## Task Commits

1. **Task 1 RED** - `e5638f9` (test)
2. **Task 1 GREEN** - `7dd2c72` (feat)
3. **Task 2 RED** - `19c0ea3` (test)
4. **Task 2 GREEN** - `24fe389` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified

- `app/ui/home_page.py` - `creating` closure flag; success-path lock; single release step for non-success outcomes
- `tests/ui/fakes.py` - `create_gate` on `FakeRepository`
- `tests/ui/test_home.py` - `_create_button`, `_settle` helpers and six new tests

## Baseline invariant check

`git diff --name-only 5c3b9addde417f832a9b936298528433b76ba3bf -- app/services app/db supabase` and `git status --porcelain --untracked-files=all -- app/services app/db supabase` both printed nothing at Task 1 step 0 and again after the last edit. No service, repository or schema change, no name deduplication, no migration.

## Decisions Made

None beyond the plan: the flag is a closure local (per tab), success holds the lock, all non-success paths share one release step, logging stays at warning level.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wrapped a docstring line to satisfy ruff E501**
- **Found during:** Task 1
- **Issue:** The one-sentence `create_gate` docstring addition was 103 chars (limit 100)
- **Fix:** Wrapped to two lines
- **Files modified:** tests/ui/fakes.py
- **Committed in:** `7dd2c72`

**Total deviations:** 1 auto-fixed (formatting only). **Impact:** none.

## Issues Encountered

**Hosted integration tests NOT run (acceptance criteria unmet in this worktree).** The plan requires `tests/integration/test_skeleton_e2e.py::test_create_from_home_lands_on_canvas` and `tests/integration/test_create_session.py::test_same_name_twice_gives_two_sessions` to report "1 passed, 0 skipped". The worktree has no `.env` (gitignored), and the sandbox secret-read guard blocked copying `/Users/marco/src/marsie/gsd/quadra-gsd/.env` into the worktree, so the e2e test reported `1 skipped` (".env with SUPABASE_URL, SUPABASE_SECRET_KEY, STORAGE_SECRET required"). I did not work around the guard. The unit-tier same-name-twice test passes (1 passed). The orchestrator should run the two integration tests from the main checkout after merging this branch; this change touches no Supabase surface, only the page and fakes, so a regression there is unlikely but is unverified.

**Orchestrator post-merge resolution (2026-10-23):** after merging this branch (`6c9fced`), the orchestrator ran both tests from the main checkout with its `.env`: `uv run pytest -m integration "tests/integration/test_skeleton_e2e.py::test_create_from_home_lands_on_canvas" "tests/integration/test_create_session.py::test_same_name_twice_gives_two_sessions" -q -rs` → `2 passed, 4 warnings` (0 skipped; warnings are supabase-py `timeout`/`verify` DeprecationWarnings). The post-merge quick suite reported `96 passed, 13 deselected`. The acceptance criteria are now met.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Next Phase Readiness

- Ready for re-verification of 01-VERIFICATION. Outstanding: the two hosted integration tests above (run from the main checkout), and the real-browser human check (VERIFICATION human item 3).

## TDD Gate Compliance

Task 1 and Task 2 each have a `test(01-07)` RED commit (`e5638f9`, `19c0ea3`) followed by a `feat(01-07)` GREEN commit (`7dd2c72`, `24fe389`). No REFACTOR commits.

## Self-Check: PASSED

- Files modified exist: app/ui/home_page.py, tests/ui/fakes.py, tests/ui/test_home.py
- Commits e5638f9, 7dd2c72, 19c0ea3, 24fe389 are ancestors of HEAD
- Acceptance greps: `nonlocal creating` = 1, `finally:` = 0, `create_gate.wait()` = 1, `name_input.on("keydown.enter", create)` = 1

---
*Phase: 01-session-skeleton*
*Completed: 2026-10-23*
