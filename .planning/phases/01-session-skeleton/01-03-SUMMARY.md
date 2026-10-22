---
phase: 01-session-skeleton
plan: 03
subsystem: api
tags: [validation, nicegui, supabase, rls, postgrest, tdd, pytest]

requires:
  - phase: 01-session-skeleton
    provides: "SessionService/Repository/tokens/home+canvas pages, integration fixtures, hosted schema (plan 01-02)"
provides:
  - "validate_project_name / InvalidProjectName / PROJECT_NAME_ERROR in app.services.sessions (trim + 1-100 code points, parity with DB char_length)"
  - "SessionService.get regex pre-filter: malformed links return None with zero repository calls"
  - "SessionService.create_session one-shot retry on APIError 23505 only"
  - "Home page inline validation, Enter-to-submit, Create disabled while in flight"
  - "tests/ui/fakes.py: FakeRepository + install_fake_services() + SEEDED_* constants (reused by 01-06)"
  - "Live tests for atomic create, DB-side rejection and publishable-key denial"
affects: [01-04, 01-05, 01-06]

plan_head_before: 5f1344543a67c0d708384748e66c0b7e90ef0d74
plan_head_after: f9d560b45186c47fb0428c1e5bb9a85d0ddb3b70

actuals:
  tokens: 5150
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Service-level validation mirrors DB CHECKs (code-point length), proven by parity tests on both sides"
    - "UI tests inject the REAL SessionService over an in-memory FakeRepository with call counters and injectable failure codes"
    - "Malformed ids short-circuit in the service so the uniform 404 never probes the database"

key-files:
  created:
    - tests/ui/fakes.py
    - tests/unit/test_tokens.py
    - tests/unit/test_sessions_service.py
    - tests/ui/test_home.py
    - tests/ui/test_not_found.py
    - tests/integration/test_create_session.py
    - tests/integration/test_rls_denies_anon.py
  modified:
    - app/services/sessions.py
    - app/ui/home_page.py

key-decisions:
  - "Retry only on 23505 and only once; every other APIError (23514, 42501) propagates immediately"
  - "Tests access the installed service through app.deps.get_services() rather than the app.deps module attribute (module attribute lookup was order dependent in the full suite)"
  - "Cleanup verification done by a one-off select after the run (0 leftover rows) instead of an in-test assertion"

requirements-completed: [SESS-01, SESS-02, SESS-03, SESS-04, SESS-05]

coverage:
  - id: D1
    description: "Empty, whitespace-only and over-100-character project names are rejected inline on the home page ('Required (max 100 characters)') and no session is created; Enter submits; valid name lands on the canvas"
    requirement: SESS-01
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_home.py (4 tests incl. test_invalid_name_shows_inline_error_and_creates_nothing, test_enter_key_creates_and_navigates)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Project-name length counts code points after trimming, identical in SessionService and in the database CHECK (100 x 'e-acute' accepted, 101 rejected with 23514)"
    requirement: SESS-01
    verification:
      - kind: unit
        ref: "tests/unit/test_sessions_service.py#test_validate_project_name"
        status: pass
      - kind: integration
        ref: "tests/integration/test_create_session.py#test_project_name_length_parity_in_code_points"
        status: pass
    human_judgment: false
  - id: D3
    description: "Same project name twice yields two distinct, openable sessions; a 23505 collision is retried once with a fresh token, a second collision or any other APIError propagates"
    requirement: SESS-01
    verification:
      - kind: unit
        ref: "tests/unit/test_sessions_service.py#test_same_name_twice_gives_two_distinct_openable_sessions"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sessions_service.py#test_collision_is_retried_once_with_a_fresh_token"
        status: pass
      - kind: integration
        ref: "tests/integration/test_create_session.py#test_same_name_twice_gives_two_sessions"
        status: pass
    human_judgment: false
  - id: D4
    description: "The Create button is disabled while a create request is in flight so a double-click yields exactly one session"
    requirement: SESS-01
    verification: []
    human_judgment: true
    rationale: "Backstop truth: the NiceGUI simulated user cannot interleave two clicks inside one in-flight await, so the guard (create_button.disable()/enable() in finally) is verified by code inspection only"
  - id: D5
    description: "Session ids carry 128 random bits: 1000 samples distinct, 22 URL-safe chars, 16 decoded bytes; the DB refuses a malformed token with 23514 and leaves no rows"
    requirement: SESS-02
    verification:
      - kind: unit
        ref: "tests/unit/test_tokens.py#test_new_session_id_is_128_bit_url_safe_and_unique"
        status: pass
      - kind: integration
        ref: "tests/integration/test_create_session.py#test_failed_create_leaves_no_rows"
        status: pass
    human_judgment: false
  - id: D6
    description: "A successful create yields an open session with exactly four quadrants IS, IS_NOT, DOES, DOES_NOT at positions 1-4; a failed create leaves no workspace or quadrant rows"
    requirement: SESS-03
    verification:
      - kind: integration
        ref: "tests/integration/test_create_session.py#test_create_session_creates_open_session_with_four_quadrants"
        status: pass
      - kind: integration
        ref: "tests/integration/test_create_session.py#test_failed_create_leaves_no_rows"
        status: pass
    human_judgment: false
  - id: D7
    description: "Malformed and unknown well-formed /s/{id} both return HTTP 404 'Session not found'; malformed ids make zero repository calls"
    requirement: SESS-05
    verification:
      - kind: automated_ui
        ref: "tests/ui/test_not_found.py#test_malformed_id_returns_404_without_db_call"
        status: pass
      - kind: automated_ui
        ref: "tests/ui/test_not_found.py#test_unknown_well_formed_id_returns_404"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sessions_service.py#test_get_prefilters_malformed_ids_without_repository_call"
        status: pass
    human_judgment: false
  - id: D8
    description: "The publishable (public) key is denied by the database: create_session RPC and workspaces select both fail with 42501 permission denied"
    requirement: SESS-04
    verification:
      - kind: integration
        ref: "tests/integration/test_rls_denies_anon.py#test_publishable_key_cannot_call_create_session"
        status: pass
      - kind: integration
        ref: "tests/integration/test_rls_denies_anon.py#test_publishable_key_cannot_read_workspaces"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-10-22
status: complete
---

# Phase 1 Plan 03: Validation, Link Hardening and Live Access Proof Summary

**Project-name validation in code-point parity with the DB CHECK, a no-DB-call 404 pre-filter for malformed links, one-shot 23505 token-collision retry, and live hosted-Supabase proofs of atomic session creation and publishable-key denial (42501)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-10-22T21:30:47Z
- **Completed:** 2026-10-22T21:33:40Z
- **Tasks:** 2
- **Files modified:** 9 (7 created, 2 modified)

## Accomplishments

- `validate_project_name` (trim, 1-100 code points) used by the home form and `SessionService.create_session`; blank or oversized names never reach the repository.
- `SessionService.get` returns None for ids failing `SESSION_ID_RE` before any repository call (uniform 404, no DB probing).
- `create_session` retries exactly once on `APIError.code == "23505"` with a fresh token; 23514 and a second 23505 propagate.
- Home page: inline `Required (max 100 characters)`, Enter-to-submit, Create disabled while in flight.
- `tests/ui/fakes.py` provides `FakeRepository` (mimics CHECKs and unique session_id, call counters, injectable error codes) and `install_fake_services()` for 01-06.
- Live proofs: atomic create (open + 4 quadrants), failed create leaves no rows, duplicate token 23505, 100/101 code-point parity, and the publishable key gets 42501 on both the RPC and a table select.

## Test results

- `test_rls_denies_anon.py` RAN (not skipped): `SUPABASE_PUBLISHABLE_KEY` present (prefix `sb_publishable_`, length 46; value never printed). Observed APIError codes: `42501` for `create_session` RPC and `42501` for `workspaces` select (asserted in the tests).
- `uv run pytest -m integration tests/integration/test_create_session.py tests/integration/test_rls_denies_anon.py -q -rs`: 7 passed, 0 skipped.
- Named-test command (a) and (b): 2 passed.
- `uv run pytest -m integration -q -rs`: 10 passed.
- `uv run pytest -q`: 38 passed, 10 deselected. `ruff check` and `ruff format --check`: clean.
- Cleanup check after the integration run: `workspaces` has 0 rows with `project_name` like `IT %` or `é%` (0 rows in total).

## Task Commits

1. **Task 1: Name validation, malformed-link 404 without DB access, collision retry (TDD)**
   - `e0c86de` test(01-03): RED, failing tests plus `FakeRepository`
   - `3210f35` feat(01-03): GREEN, service and home page changes
   - REFACTOR: none.
2. **Task 2: Atomic creation, DB-side validation, publishable-key denial** - `f9d560b` (test)

**Plan metadata:** recorded in the following docs commit.

## TDD (Task 1)

- **RED:** 19 of 27 tests failed. Evidence was a pytest JUnit XML report passed to `gsd check tdd-red-evidence` with target `test_malformed_id_returns_404_without_db_call`; verdict `RED_EVIDENCE_OK`, reason `target_test_failed`. Semantic assessment: the target executed and failed on the planned assertion (`assert 1 == 0`: the repository was called for a malformed id). The other failures were the missing `validate_project_name`/`InvalidProjectName` (imported inside test bodies so collection stayed valid), missing inline validation and missing retry. The 8 tests that passed in RED are the token tests (the generator exists since 01-02) and the parts of existing behavior (unknown id 404, valid create, same name twice). Temporary record files were removed.
- **GREEN:** minimal implementation; 27 passed.
- **REFACTOR:** none.

## Files Created/Modified

- `app/services/sessions.py` - validation, 23505 retry, regex pre-filter (constructor unchanged)
- `app/ui/home_page.py` - inline validation, Enter-to-submit, in-flight disable
- `tests/ui/fakes.py` - FakeRepository, install_fake_services, SEEDED_* constants
- `tests/unit/test_tokens.py`, `tests/unit/test_sessions_service.py` - token and service behavior
- `tests/ui/test_home.py`, `tests/ui/test_not_found.py` - home form and 404 behavior
- `tests/integration/test_create_session.py`, `tests/integration/test_rls_denies_anon.py` - live proofs

## Decisions Made

- Retry only on 23505 and only once (any other code propagates immediately).
- Tests reach the installed service via `get_services()`; `import app.deps` inside a test function raised "module 'app' has no attribute 'deps'" in the full suite, depending on collection order.
- Left-over-row check done by a post-run select rather than an in-test assertion (allowed by the plan).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in test] Order-dependent `app.deps` attribute access in the service tests**
- **Found during:** Task 1 GREEN (full-suite run)
- **Issue:** Tests passed when run alone but 4 failed in the full suite with `module 'app' has no attribute 'deps'` (function-local `import app.deps` combined with NiceGUI's own `app` name).
- **Fix:** Use `from app.deps import get_services` and `get_services().sessions`.
- **Files modified:** tests/unit/test_sessions_service.py
- **Verification:** full suite 38 passed.
- **Committed in:** 3210f35

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** None. Test-only fix; no scope change.

## Issues Encountered

- The double-click guard (`Create` disabled in flight) cannot be exercised by the NiceGUI simulated user, so it remains a backstop truth verified by code inspection (coverage D4 is `human_judgment: true`).
- Pre-existing supabase-py DeprecationWarnings (`timeout`, `verify`) appear in integration runs; out of scope.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface beyond the plan's threat model; T-01-10, T-01-11 and T-01-12 are mitigated and test-proven. No packages installed; `uv.lock` unchanged (T-01-SC).

## User Setup Required

Completed by the human before execution: `SUPABASE_PUBLISHABLE_KEY` in `.env`. No further configuration.

## Next Phase Readiness

- 01-06 can import `tests/ui/fakes.py` (`install_fake_services`, `SEEDED_ID_A/B`, `SEEDED_NAME_A/B`) unchanged.
- `SessionService(repository)` constructor and method signatures are unchanged for 01-05.
- Per-SESS-04 fresh-browser UI test is written in 01-06 as planned.

## Self-Check: PASSED

- Files exist: all 9 key files present on disk.
- Commits exist and are ancestors of HEAD: e0c86de, 3210f35, f9d560b.
- `commits: 3` measured with `git rev-list --count 5f1344543a67c0d708384748e66c0b7e90ef0d74..HEAD`.

---
*Phase: 01-session-skeleton*
*Completed: 2026-10-22*
