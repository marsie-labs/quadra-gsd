---
phase: 01-session-skeleton
verified: 2026-10-23T00:00:00Z
status: human_needed
score: 20/20 must-haves verified
covered_files:
  - ".planning/phases/01-session-skeleton/01-01-PLAN.md"
  - ".planning/phases/01-session-skeleton/01-01-SUMMARY.md"
  - ".planning/phases/01-session-skeleton/01-02-PLAN.md"
  - ".planning/phases/01-session-skeleton/01-02-SUMMARY.md"
  - ".planning/phases/01-session-skeleton/01-03-PLAN.md"
  - ".planning/phases/01-session-skeleton/01-03-SUMMARY.md"
  - ".planning/phases/01-session-skeleton/01-04-PLAN.md"
  - ".planning/phases/01-session-skeleton/01-04-SUMMARY.md"
  - ".planning/phases/01-session-skeleton/01-05-PLAN.md"
  - ".planning/phases/01-session-skeleton/01-05-SUMMARY.md"
  - ".planning/phases/01-session-skeleton/01-06-PLAN.md"
  - ".planning/phases/01-session-skeleton/01-06-SUMMARY.md"
  - ".planning/phases/01-session-skeleton/01-07-PLAN.md"
  - ".planning/phases/01-session-skeleton/01-07-SUMMARY.md"
  - "README.md"
  - "app/main.py"
  - "app/realtime/hub.py"
  - "app/services/sessions.py"
  - "app/ui/canvas_page.py"
  - "app/ui/home_page.py"
  - "app/ui/identity.py"
  - "supabase/migrations/20261022000000_init_schema.sql"
  - "tests/ui/fakes.py"
  - "tests/ui/test_home.py"
covered_digest: "v3:sha256:114c349da0f36be5fbebadd6193ca88aca5424ec94e96dfa887ad93eb7d728e9"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 12/13
  gaps_closed:
    - "The Create button is disabled while a create request is in flight, so a double-click produces exactly one session (01-03 backstop truth; REVIEW WR-01)"
  gaps_remaining: []
  regressions: []
deferred: []
human_verification:
  - test: "Follow README.md from a clean checkout (clone, cp .env.example .env, fill keys, supabase db push --linked, uv run python -m app)"
    expected: "The app starts as a single worker and the console shows 'Realtime startup check verified ... ms'"
    why_human: "Needs the developer's own Supabase keys and a fresh clone. The README text was checked against the code but never executed from a clean checkout."
  - test: "Create a session in browser A, open the link in a private window or second profile (browser B), set different names, and reload both"
    expected: "Both browsers show the same project name and IS / IS NOT / DOES / DOES NOT. Each is prompted independently and keeps its name after a reload. No login prompt appears."
    why_human: "Real cookies and profiles. Only the NiceGUI simulated-browser fixture exercised this."
  - test: "In a real browser, press Enter twice quickly (or hold Enter) in the project name field, and double-click Create"
    expected: "Exactly one session is created and the browser lands on it. The Create button is greyed out from the first trigger."
    why_human: "The server-side flag is proven by tests that fire two events through NiceGUI's own handler path, but the simulated user does not model real DOM event delivery or key repeat. Not expected to fail; this is the end-of-phase real-browser confirmation the plan deferred."
  - test: "Visual and UX check of the banner, header name and 2x2 grid (UI-REVIEW scored 15/24)"
    expected: "Banner is inline and ignorable; the grid is usable at narrow widths"
    why_human: "Visual appearance cannot be checked in code."
---

# Phase 1: Session Skeleton Verification Report

**Phase Goal:** A user can create a session, share its unguessable link, and teammates can open it, enter a display name, and see the four labeled quadrants. The schema, project setup and Realtime connection are proven underneath.
**Verified:** 2026-10-23
**Status:** human_needed
**Re-verification:** Yes, after gap closure (plan 01-07)
**Mode:** mvp (the ROADMAP goal is not in user-story form, so User Flow Coverage was derived from the five success criteria, as in the first report)

## Goal Achievement

The one gap from the first verification is closed. Every automated check passes and nothing regressed. The status is `human_needed` only because four manual checks remain (README reproduction from a clean checkout, a real two-browser walkthrough, a real-browser double Enter and double click, and a visual pass). None of them is a code gap.

### Gap closure evidence (the double-submit gap)

I read `app/ui/home_page.py` as it stands. `create()` now:

- declares `nonlocal creating` and returns at once if `creating` is true, or if `name_input.validate()` fails (checked before any await);
- sets `creating = True` and calls `create_button.disable()` before the single `await` of `create_session`;
- on success runs `ui.navigate.to(...)` and `return`s, so it does not clear the flag or re-enable the button;
- on `InvalidProjectName` sets `name_input.error`, and on any other `Exception` logs a warning and notifies. Both fall through to `creating = False` and `create_button.enable()`.

The flag is a closure local of `home()`, so it belongs to one page instance. `grep -c "finally:"` returns 0. The Enter wiring (`name_input.on("keydown.enter", create)`) is still present once, so Enter and click share the one guarded handler.

**Mutation check (my own run).** I restored the pre-fix `home_page.py` from baseline commit `5c3b9ad` over the working copy, ran `tests/ui/test_home.py`, then put the fixed file back (`git status` clean for `app/` and `tests/` afterwards). Result with the old code: 3 failed, 8 passed. The failures were `test_double_enter_while_in_flight_creates_one_session`, `test_double_click_while_in_flight_creates_one_session` and `test_create_stays_locked_after_success_until_navigation` (`assert not True` on `button.enabled`). With the fix: 11 passed. So the new tests detect the original defect and are not vacuous. The failure-release, rejected-name and two-browser tests pass on both versions, as the plan said (they are guards).

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | SC1: A user enters a project name on `/` and lands on `/s/<session_id>`, a 128-bit token | VERIFIED | `tokens.py` is `secrets.token_urlsafe(16)`. `home_page.py` calls `sessions.create_session` then `ui.navigate.to`. `test_valid_name_creates_and_lands_on_canvas` passes. Live `test_create_from_home_lands_on_canvas` passed in this run. |
| 2  | SC2: A second browser with no login opens the same session and sees IS, IS NOT, DOES, DOES NOT | VERIFIED (simulated browser) | Unchanged since the first report. `test_canvas.py` two-user test passes in the quick suite. Real browser is a human item. |
| 3  | SC3: First-time visitor is prompted for a display name; after a reload they are not asked again | VERIFIED (simulated browser) | `test_identity.py` and the 1-year cookie assertion pass (quick suite and live suite). |
| 4  | SC4: An unknown `session_id` shows a not-found page | VERIFIED | `test_not_found.py` and the live not-found integration test pass. |
| 5  | SC5: README setup works and a startup check confirms DB change events reach the Python server | VERIFIED (startup check); README reproduction is a human item | Full live suite re-run: 13 passed, 0 skipped, including the hub round trip and the real-subprocess startup test. |
| 6  | SESS-03: One RPC creates the workspace and exactly four quadrants atomically | VERIFIED | `test_create_session.py` live. Migration unchanged since baseline. |
| 7  | SESS-04 / access model: no login; anon key denied by the DB | VERIFIED | `test_rls_denies_anon.py` live. |
| 8  | QUAL-04 prohibition: the Realtime check is never reported verified unless this run's nonce event arrived | VERIFIED | `hub.py` unchanged; hub unit tests pass; live test passes. |
| 9  | IDEN-01: inline, ignorable name banner; `ensure_display_name()` contract | VERIFIED | Banner and `test_ensure_name.py` tests pass in the quick suite. |
| 10 | IDEN-02 / D-03: a stored name is never overwritten; header is read-only | VERIFIED | `test_identity.py` passes. |
| 11 | No data polling | VERIFIED | No `ui.timer` in `app/`. The grep for TBD / FIXME / XXX / TODO / HACK over `app`, `tests`, `supabase` and `README.md` returned nothing. |
| 12 | The Create button is disabled while a create is in flight, so a double-click produces exactly one session (01-03 backstop truth; was FAILED) | VERIFIED | Both double-trigger tests assert `create_calls == 1` and `not _create_button(user).enabled` while the gate holds the call open, then `len(repo.rows) == 2` after release. Mutation check above shows they fail on the old code. See the note on real-browser delivery under Human Verification. |
| 13 | DB rejects a card whose author is empty or over 40 characters | VERIFIED, with warning | Live `test_card_author_check.py` passes. WR-07 (no `btrim` in the CHECK) is unchanged and still open. |
| 14 | 01-07 T1: double Enter while a create is in flight makes one `create_session` call and one session, and the browser lands on that canvas | VERIFIED | `test_double_enter_while_in_flight_creates_one_session` passes. It asserts the canvas marker `project-name` shows "Twice Enter". |
| 15 | 01-07 T2: two clicks before the first handler runs make one call and one session | VERIFIED | `test_double_click_while_in_flight_creates_one_session` passes. It issues two synchronous `.click()` calls, which reproduces the race the planner described. |
| 16 | 01-07 T3 (same as truth 12): button reports enabled False while in flight | VERIFIED | Counted once, under truth 12. |
| 17 | 01-07 T4: after success the form stays locked; a further Enter makes no call | VERIFIED | `test_create_stays_locked_after_success_until_navigation` passes. It asserts on the stale button and field, so it exercises the real handler. It failed on the old code. |
| 18 | 01-07 T5: a failed create releases the lock and a retry lands on the canvas | VERIFIED | `test_failed_create_releases_the_lock_for_a_retry` passes (APIError 42501, notify text shown, button enabled, second call lands, `create_calls == 2`). |
| 19 | 01-07 T6: the lock is per page instance; two browsers each get their own session | VERIFIED | `test_two_browsers_creating_at_once_each_get_their_own_session` passes (2 calls, 3 rows). The flag is a closure local, not module level. |
| 20 | 01-07 T7 and T8: same name twice gives two distinct sessions; a server-side `InvalidProjectName` also releases the lock | VERIFIED | `test_same_name_twice_gives_two_distinct_openable_sessions` (unit) and the live `test_same_name_twice_gives_two_sessions` pass. `test_rejected_name_releases_the_lock_for_a_retry` passes (error shown, `create_calls == 0`, button enabled, retry lands). |

**Score:** 20/20 truths verified (13 carried from the first report, including the formerly failed truth 12, plus 7 new from 01-07; 01-07's third truth duplicates truth 12). 0 are present-but-behavior-unverified.

Behavior-dependent truths (a re-entrancy and ordering invariant) are not accepted on presence alone here. Each has a named test that exercises the transition, and the mutation check proves those tests fail without the fix.

### 01-07 prohibition (SESS-01, test tier)

"MUST NOT stop duplicate creates by deduplicating on project name in the service, repository or database." Status: VERIFIED, so it is not an `unverified-prohibition` flag.

- The unit same-name-twice test and the live same-name-twice test both pass. A name-keyed or time-window dedup would return the existing session and fail them.
- `git diff --name-only 5c3b9addde417f832a9b936298528433b76ba3bf -- app/services app/db supabase` printed nothing, and `git status --porcelain --untracked-files=all -- app/services app/db supabase` printed nothing. `git diff --stat 5c3b9ad HEAD -- app tests supabase` lists only `app/ui/home_page.py`, `tests/ui/fakes.py` and `tests/ui/test_home.py`.

### 01-07 edge coverage

| Category | Disposition in plan | Verified |
|----------|--------------------|----------|
| idempotency | truths 1-4 and 7 | Yes: double Enter, double click and stays-locked tests, plus both same-name-twice tests |
| concurrency | truths 5, 6 and 8 | Yes: failure-release, rejected-name-release and two-browser tests |
| empty, encoding | flagged assumptions, owned by 01-03 | Unchanged. `test_invalid_name_shows_inline_error_and_creates_nothing` (3 cases) still passes. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/ui/home_page.py` | create() guarded by `nonlocal creating` | VERIFIED | Substantive, wired from `register_pages()`, and behavior proven by 6 new tests. |
| `tests/ui/fakes.py` | `FakeRepository.create_gate` | VERIFIED | `create_gate` appears 4 times; `create_gate.wait()` appears once. The default is None, so older tests are unaffected (all pass). |
| `tests/ui/test_home.py` | six new double-trigger and lock-lifecycle tests | VERIFIED | 11 tests pass; all six named tests exist. |
| All 01-01 to 01-06 artifacts | as in the first report | VERIFIED | Unchanged (no diff to them since baseline apart from the three files above). Quick and live suites pass. |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `home_page.create()` flag | `SessionService.create_session` | `creating` is checked and set before the only await | WIRED |
| Enter and Create button | one guarded `create()` | `name_input.on("keydown.enter", create)` and `ui.button("Create", on_click=create)` | WIRED |
| `test_home.py` | `fakes.py` | `repo.create_gate` holds the first call open | WIRED |
| All earlier key links (home to service, canvas to service, canvas to identity, lifespan to hub, `ui.run_with` last, `__main__` to `uvicorn.run(workers=1)`) | | | WIRED, no change |

### Data-Flow Trace (Level 4)

Unchanged from the first report. `canvas_page` data comes from `SessionService.get`, through the repository to PostgREST, and the live e2e test passed in this run. The new lock state is purely local and gates the single service call. No hollow props or static returns.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Quick suite | `uv run python -m pytest -q --tb=short -rs` | 96 passed, 13 deselected | PASS |
| Home tests | `uv run pytest tests/ui/test_home.py -q` | 11 passed | PASS |
| Home tests against the pre-fix `home_page.py` (mutation) | same command, baseline file swapped in, then restored | 3 failed, 8 passed (double Enter, double click, stays-locked) | PASS (detects the defect) |
| Live integration suite | `uv run pytest -q -m integration -rs` | 13 passed, 0 skipped | PASS |
| Hosted create-from-home and same-name-twice | the two named integration tests | 2 passed | PASS |
| Unit same-name-twice | named test | 1 passed | PASS |
| Lint and format | `uv run ruff check .` and `uv run ruff format --check .` | All checks passed; 38 files already formatted | PASS |

### Probe Execution

Step 7c: SKIPPED. No probe scripts are declared or present. The Realtime probe is exercised by the live pytest suite above.

### Requirements Coverage

Every requirement ID found in the plan frontmatter appears in REQUIREMENTS.md and maps to Phase 1: 01-01 [QUAL-04]; 01-02 [SESS-01..05, QUAL-04]; 01-03 [SESS-01..05]; 01-04 [QUAL-04]; 01-05 [QUAL-04, IDEN-02]; 01-06 [SESS-04, IDEN-01, IDEN-02]; 01-07 [SESS-01]. The union is exactly the eight ROADMAP IDs. None is orphaned. Phase 2's IDEN-03 is not claimed here.

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| SESS-01 | 01-02, 01-03, 01-07 | Create a session by project name, land on its link | SATISFIED | Truths 1, 12, 14-20. The duplicate-create defect is closed. |
| SESS-02 | 01-02, 01-03 | Unguessable >=128-bit `session_id` | SATISFIED | `tokens.py`, DB CHECK, `test_tokens.py`. |
| SESS-03 | 01-02, 01-03 | New session open with four quadrants, atomic | SATISFIED | Truth 6. |
| SESS-04 | 01-02, 01-03, 01-06 | Anyone with the link can open it, no login | SATISFIED (simulated browser) | Truths 2 and 7. |
| SESS-05 | 01-02, 01-03 | Unknown link shows not-found | SATISFIED | Truth 4. |
| IDEN-01 | 01-06 | First visit prompts for display name | SATISFIED (simulated browser) | Truth 9. |
| IDEN-02 | 01-05, 01-06 | Name remembered across reloads and sessions | SATISFIED (simulated browser) | Truths 3 and 10. |
| QUAL-04 | 01-01, 01-02, 01-04, 01-05 | Runs locally with documented setup | SATISFIED, README reproduction is a human item | Truths 5, 8 and 11. |

Tracking note: `.planning/REQUIREMENTS.md` still shows these eight as unchecked (`[ ]`) with traceability status "Gaps Found". That is bookkeeping left over from the first report. It should be flipped by the orchestrator once the phase is accepted; the verifier does not edit it.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/ui/home_page.py` | 16-37 | None. The earlier re-entrancy gap and the `finally` re-enable are gone. | none | |
| `app/ui/canvas_page.py` | 13 | Unguarded `await sessions.get(...)` (WR-05) | Warning, unchanged | A transient DB error shows NiceGUI's generic 500 page for a valid link. |
| `app/ui/identity.py` | 68, 104 | Non-idempotent `delete()` (WR-06) | Warning, unchanged | |
| `supabase/migrations/...sql` | 13, 34 | CHECKs lack `btrim` (WR-07) | Warning, unchanged | Add a forward migration before Phase 2 writes cards. |
| `app/realtime/hub.py`, `app/settings.py` | | WR-02, WR-03, WR-04 | Warning, unchanged | Log and validation-message secret handling; connect timeout. |

No debt markers (TBD, FIXME, XXX, TODO, HACK) were found. The remaining REVIEW items are tracked in `01-REVIEW-DISPOSITION.md`; WR-01 is now closed by 01-07. They are not must-have failures.

Minor observation, not a finding: `except Exception` does not catch `asyncio.CancelledError`. If a client disconnects mid-create, the flag stays set on a page that no longer exists, which is harmless.

### Human Verification Required

See the `human_verification` list in the frontmatter:

1. Run the README from a clean checkout.
2. Do the real two-browser walkthrough (end-of-phase human check).
3. Try double Enter and double click in a real browser. The guard no longer depends on the DOM disabled state, because the server-side flag rejects the second event, so a pass is expected. This is confirmation of real event delivery, not an open defect.
4. Visual and UX pass (UI-REVIEW 15/24).

### Gaps Summary

No gaps. The double-submit defect from the first report is closed. The code is correct as read, and six new tests cover it. Three of them fail against the old code and pass against the new, and the full quick suite, the live suite, ruff and the baseline-invariant check are all clean. All 13 earlier truths still hold, with no regressions. The phase is ready for the end-of-phase human checks. Warnings WR-02 to WR-07 remain open as before; WR-07 is worth doing before Phase 2.

---

_Verified: 2026-10-23_
_Verifier: Claude (gsd-verifier)_
