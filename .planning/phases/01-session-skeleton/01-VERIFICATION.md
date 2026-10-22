---
phase: 01-session-skeleton
verified: 2026-10-22T00:00:00Z
status: gaps_found
score: 12/13 must-haves verified
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
  - "README.md"
  - "app/main.py"
  - "app/realtime/hub.py"
  - "app/services/sessions.py"
  - "app/ui/canvas_page.py"
  - "app/ui/home_page.py"
  - "app/ui/identity.py"
  - "supabase/migrations/20261022000000_init_schema.sql"
covered_digest: "v3:sha256:73f46079621cdb22e28fab035925bd8e7c7be8070b8961bb8ceec7a1697f6b2a"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The Create button is disabled while a create request is in flight, so a double-click produces exactly one session (01-03 plan truth, verification: backstop)"
    status: partial
    reason: "The guard covers only the button. The Enter handler re-enters create() while the first RPC is awaiting, so a double Enter makes two sessions. Reproduced with a scratch UI test (a 0.5 s slow fake repository, two keydown.enter triggers): create_session was called 2 times. The finally clause also re-enables the button on the success path before ui.navigate.to runs. The guarantee is only code-inspected (SUMMARY marked it human_judgment) and no test covers a double trigger. The roadmap success criterion (create and land on /s/<id>) still works; the defect is duplicate orphan sessions (REVIEW WR-01)."
    artifacts:
      - path: "app/ui/home_page.py"
        issue: "create() has no re-entrancy flag; name_input.on('keydown.enter', create) bypasses the button disable; finally: create_button.enable() runs on success before navigation"
      - path: "tests/ui/test_home.py"
        issue: "Only asserts create_calls == 1 for a single click or single Enter; no double-trigger test"
    missing:
      - "A re-entrancy flag independent of the button (nonlocal creating); stay locked after a successful create until navigation"
      - "A UI test that fires keydown.enter twice (and click twice) against a slow fake repository and asserts create_calls == 1"
deferred: []
human_verification:
  - test: "Follow README.md from a clean checkout (clone, cp .env.example .env, fill keys, supabase db push --linked, uv run python -m app)"
    expected: "The app starts as a single worker and the console shows 'Realtime startup check verified ... ms'"
    why_human: "Needs the developer's own Supabase keys and a fresh clone. The README text was checked against the code (env vars, ports, check modes, stages all match) but never executed from a clean checkout."
  - test: "Create a session in browser A, open the link in a private window or second profile (browser B), set different names, and reload both"
    expected: "Both browsers show the same project name and IS / IS NOT / DOES / DOES NOT. Each is prompted independently and keeps its name after a reload. No login prompt appears."
    why_human: "Real cookies and profiles. Only the NiceGUI simulated-browser fixture exercised this."
  - test: "In a real browser, press Enter twice quickly in the project name field, and double-click Create"
    expected: "Exactly one session is created"
    why_human: "The simulated user does not model the disabled DOM button. Currently expected to fail on the Enter path (see gap)."
  - test: "Visual and UX check of the banner, header name and 2x2 grid (UI-REVIEW scored 15/24)"
    expected: "Banner is inline and ignorable; the grid is usable at narrow widths"
    why_human: "Visual appearance cannot be checked in code."
---

# Phase 1: Session Skeleton Verification Report

**Phase Goal:** A user can create a session, share its unguessable link, and teammates can open it, enter a display name, and see the four labeled quadrants. The schema, project setup and Realtime connection are proven underneath.
**Verified:** 2026-10-22
**Status:** gaps_found
**Re-verification:** No, initial verification
**Mode:** mvp (the ROADMAP goal is not in user-story form, so User Flow Coverage was derived from the five success criteria)

## Goal Achievement

All five ROADMAP success criteria hold in the code and tests. One plan-level must-have (the double-submit guarantee) is demonstrably false, so the status is `gaps_found` per the decision tree. The gap is narrow and cheap to close. It does not stop a user from creating a session and landing on its link.

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | SC1: A user enters a project name on `/` and lands on `/s/<session_id>`, a 128-bit token | VERIFIED | `app/tokens.py` is `secrets.token_urlsafe(16)` (22 chars, 16 bytes). `app/ui/home_page.py` calls `sessions.create_session` then `ui.navigate.to("/s/...")`. `tests/ui/test_home.py::test_valid_name_creates_and_lands_on_canvas` and integration `test_skeleton_e2e::test_create_from_home_lands_on_canvas` pass. The DB CHECK is `^[A-Za-z0-9_-]{22,64}$`. |
| 2  | SC2: A second browser with no login opens the same session and sees IS, IS NOT, DOES, DOES NOT | VERIFIED (simulated browser) | `canvas_page.py` renders four `quadrant-<kind>` cards from DB rows with `QUADRANT_LABELS`. `tests/ui/test_canvas.py::test_second_browser_opens_same_session_without_login` uses two independent users and asserts no login prompts. RLS test confirms the publishable key is denied, so no browser key exists. Real-browser check is in the human list. |
| 3  | SC3: First-time visitor is prompted for a display name; after a reload they are not asked again and the name is shown | VERIFIED (simulated browser) | `identity.py` stores the name in `app.storage.user`. `canvas_page.py` shows `name_banner` only when `current_name()` is None. The `test_identity.py` reload test passes. `main.py` sets cookie `max_age` to 1 year; the integration subprocess test asserts `max-age=31536000`. |
| 4  | SC4: An unknown `session_id` shows a not-found page | VERIFIED | `canvas_page.py` sets `status_code = 404` with "Session not found" and a link to `/`. `SessionService.get` pre-filters malformed ids without a DB call. `test_not_found.py` (2 tests) and the integration test against the real DB pass. |
| 5  | SC5: Developer can follow the README to set env vars, apply migrations and start the app (single worker); a startup check confirms DB change events reach the Python server | VERIFIED (startup check); README reproduction is a human item | `README.md` has Prerequisites, Configure, migrations, Run and Startup Realtime check sections. `__main__.py` runs `uvicorn.run(..., workers=1)`. `main.py` lifespan awaits `hub.run_startup_check`. I re-ran `pytest -m integration` against hosted Supabase: 13 passed, including `test_probe_roundtrip_via_hub` and `test_app_starts_and_proves_realtime` (real subprocess server). |
| 6  | SESS-03: One RPC creates the workspace and exactly four quadrants atomically; failed creates leave no rows | VERIFIED | The migration's `create_session` is plpgsql, so it is transactional. `tests/integration/test_create_session.py` passes. |
| 7  | SESS-04 / access model: No login anywhere; anon/publishable key denied by the DB; browsers never receive a Supabase key | VERIFIED | Migration has RLS enabled on all tables, `revoke ... from anon, authenticated`, and execute on the RPC granted to `service_role` only. `test_rls_denies_anon.py` passes live. Pages call only `SessionService`. |
| 8  | QUAL-04 prohibition: the Realtime check is never reported verified unless this run's nonce event arrived | VERIFIED | `hub.py::run_startup_check` sets `verified` only after `verify_roundtrip` returns. Tests `test_subscribed_alone_never_verifies`, `test_non_matching_nonce_leaves_waiter_pending` and `test_strict_check_failure_raises_with_stage_and_fix` pass. The live negative control is recorded in the 01-04 SUMMARY. |
| 9  | IDEN-01: Inline, ignorable name banner (no blocking modal); `ensure_display_name()` returns the stored name, a dialog-collected name, or None on Cancel | VERIFIED | `canvas_page.py` renders the banner alongside the grid. `test_first_visit_shows_banner_over_a_fully_visible_canvas` and the 4 `test_ensure_name.py` tests pass. There is no `Anonymous` string in `app/`. |
| 10 | IDEN-02 / D-03: A stored name is never overwritten by a stale banner; display is read-only | VERIFIED | `save_display_name` returns the existing name first (`tests/unit/test_identity.py::test_save_never_overwrites_an_existing_name`). The header is a `ui.label` with no input. |
| 11 | No data polling (CLAUDE.md constraint) | VERIFIED | `grep` finds no `ui.timer` and no polling loop in `app/`. The only `while True` is `hub.py::verify_roundtrip`, a startup-only probe re-write loop bounded by `timeout`. `uvicorn.run` is called once. |
| 12 | Create button is disabled while a create is in flight, so a double-click produces exactly one session | FAILED (partial) | See Gaps. A double Enter produced 2 `create_session` calls in my scratch test. A double click on the button also produced 2 calls under the simulated user, which does not model the disabled DOM state, so that part is inconclusive. |
| 13 | DB rejects a card whose author is empty or over 40 characters, with the same rule as `validate_display_name` | VERIFIED, with warning | `test_card_author_check.py` passes live (empty and 41 rejected; 40 multibyte accepted). The CHECK is `char_length(author) between 1 and 40` with no `btrim`, so `'   '` is accepted at DB level while Python rejects it (REVIEW WR-07). The truth wording ("empty") is met. The "same rule" intent is not fully met. |

**Score:** 12/13 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261022000000_init_schema.sql` | Schema, RLS, atomic RPC, publication | VERIFIED | Substantive. Used live by 13 integration tests. |
| `app/db/repository.py` | `connect`, `create_session`, `get_session`, `upsert_probe` | VERIFIED | Async client only; wired into `main.py`. |
| `app/services/sessions.py` | Validation, pre-filter, one-shot 23505 retry | VERIFIED | Wired from both pages. |
| `app/ui/home_page.py` | Create form | VERIFIED with gap | Wired. Re-entrancy defect (see Gaps). |
| `app/ui/canvas_page.py` | Quadrant grid, 404, name header/banner | VERIFIED | Wired. No DB-failure handling (WR-05, warning). |
| `app/ui/identity.py` | Validation, storage, banner, gate | VERIFIED | Wired. Not idempotent on a deleted element (WR-06, warning). |
| `app/realtime/hub.py` | Nonce-matched round trip | VERIFIED | Wired in lifespan; live pass. |
| `app/main.py`, `app/__main__.py` | Composition root, `/healthz`, single worker | VERIFIED | `ui.run_with` is the last call; `workers=1`. |
| `README.md` | Setup, migrations, run, check | VERIFIED (static) | No key values in README or `.env.example`. Clean-checkout run is a human item. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| home_page | SessionService | `sessions.create_session(` | WIRED | |
| canvas_page | SessionService | `sessions.get(` | WIRED | |
| canvas_page | identity | `current_name()`, `name_banner(on_saved=...)` | WIRED | |
| main lifespan | RealtimeHub | `run_startup_check(settings.realtime_check, repo.upsert_probe)` | WIRED | |
| main | pages / NiceGUI | `register_pages()` then `ui.run_with(` last | WIRED | `/healthz` is registered before it. |
| `__main__` | main | `uvicorn.run(create_app, factory=True, workers=1)` | WIRED | |
| ui_main (test) | identity | `ensure_display_name(` | WIRED | The test-only page is absent from `app/`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| canvas_page | `view.project_name`, `view.quadrants` | `SessionService.get` -> `Repository.get_session` -> PostgREST `workspaces` select with embedded `quadrants` | Yes (integration e2e against hosted DB) | FLOWING |
| canvas_page | `current_name()` | `app.storage.user["display_name"]` | Yes (set by banner) | FLOWING |
| /healthz | `realtime` | `hub.status()` | Yes, set only by the nonce-matched event | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Quick suite | `uv run pytest -q` | 90 passed, 13 deselected | PASS |
| Live integration (hosted Supabase) | `uv run pytest -q -m integration -rs` | 13 passed, 0 skipped | PASS |
| Lint | `uv run ruff check app tests` | All checks passed | PASS |
| Double Enter creates one session (scratch test, removed afterwards) | two `keydown.enter` triggers with a 0.5 s fake RPC | `create_session` called 2 times | FAIL |
| Double click creates one session (scratch test) | two clicks with a 0.5 s fake RPC | 2 calls (the simulated user ignores the disabled state) | INCONCLUSIVE |

### Probe Execution

Step 7c: SKIPPED (no probe scripts are declared or present; the Realtime probe is exercised by the pytest integration tests above).

### Requirements Coverage

Every requirement ID in the phase's PLAN frontmatter appears in REQUIREMENTS.md and is mapped to Phase 1. None is orphaned. The only Phase-1-mapped IDs are the eight listed in the ROADMAP.

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| SESS-01 | 01-02, 01-03 | Create a session by project name, land on its link | SATISFIED | Truth 1. Duplicate creation via Enter is a robustness gap, not a failure of the requirement. |
| SESS-02 | 01-02, 01-03 | Unguessable >=128-bit `session_id` | SATISFIED | `tokens.py`, DB CHECK, `test_tokens.py` (1000 distinct, 16 bytes). |
| SESS-03 | 01-02, 01-03 | New session open with four quadrants, atomic | SATISFIED | Truth 6. |
| SESS-04 | 01-02, 01-03, 01-06 | Anyone with the link can open it, no login | SATISFIED (simulated browser) | Truths 2 and 7. |
| SESS-05 | 01-02, 01-03 | Unknown link shows not-found | SATISFIED | Truth 4. |
| IDEN-01 | 01-06 | First visit prompts for display name | SATISFIED (simulated browser) | Truth 9. |
| IDEN-02 | 01-05, 01-06 | Name remembered across reloads and sessions | SATISFIED (simulated browser) | Truths 3 and 10; the 1-year cookie is asserted live. |
| QUAL-04 | 01-01, 01-02, 01-04, 01-05 | Runs locally with documented setup (env, migrations, single worker) | SATISFIED, README reproduction is a human item | Truths 5, 8 and 11. |

Scope check: IDEN-03 (author on cards) is correctly assigned to Phase 2 and is not claimed here.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/ui/home_page.py` | 16-31, 38 | No re-entrancy guard; `finally` re-enables the button on success | Blocker for the 01-03 double-submit truth (see gap) | Duplicate sessions |
| `app/ui/canvas_page.py` | 13 | Unguarded `await sessions.get(...)` | Warning (WR-05) | A transient DB error shows NiceGUI's generic 500 page for a valid link. It does not render the 404 branch, so it never mislabels a valid link as unknown. |
| `app/ui/identity.py` | 68, 104 | `banner.delete()` and `dialog.delete()` not idempotent | Warning (WR-06) | A key-repeat Enter or a second tab can raise `ValueError` and skip `on_saved` |
| `supabase/migrations/...sql` | 13, 34 | `author` / `closed_by` CHECKs lack `btrim` | Warning (WR-07) | Whitespace-only author is accepted at DB level; needs a forward migration before Phase 2 relies on it |
| `app/realtime/hub.py`, `app/settings.py` | 28-32; 30-38 | Key-log pin is conditional; short `STORAGE_SECRET` echoed in the validation error (WR-02, WR-03) | Warning | Secret exposure in logs under non-default log levels or bad config. Not exercised in default launch. |
| `app/realtime/hub.py` | 100, 147 | No hard timeout on `connect()` / `write_probe` (WR-04) | Warning | Startup may stall past the documented ~15 s |

No TBD / FIXME / XXX / TODO / HACK markers were found in `app/`, `tests/`, the migration or the README. The remaining REVIEW items (WR-08 and IN-01 to IN-06) are unchanged and tracked in 01-REVIEW-DISPOSITION.md (14 findings, all open). They are not must-have failures.

### Human Verification Required

See the `human_verification` list in the frontmatter. In short:
1. Run the README from a clean checkout.
2. Do the real two-browser walkthrough (end-of-phase human check).
3. Try double Enter and double click in a real browser (expected to show the gap).
4. Visual and UX pass (UI-REVIEW 15/24).

### Gaps Summary

There is one gap. The 01-03 plan promised that a double-submit makes exactly one session. The code only disables the Create button. Pressing Enter twice runs `create()` twice, and on success the button is re-enabled before the browser navigates. I reproduced the double-Enter case against a slow fake repository (2 `create_session` calls). The SUMMARY disclosed this as code-inspection-only (`human_judgment: true`), and the inspection does not support the claim. REVIEW WR-01 already carries the fix: add a `creating` flag, don't re-enable on success, and add a double-trigger UI test.

This does not block anyone from creating a session, sharing the link and seeing the canvas, so the phase goal is functionally met. The gap needs closure, or an explicit override accepted by the developer, before the phase is called fully verified.

Warnings that are not gaps and need no closure before Phase 2 (some are worth doing early):
- WR-05: the canvas page has no DB-failure handling.
- WR-07: add a forward migration so `cards.author` rejects whitespace before Phase 2 starts writing cards.
- WR-02 and WR-03: secret handling in logs and validation errors.

Process note: `01-06-SUMMARY.md` has no `## Self-Check` section, unlike 01-01 to 01-05. The 01-06 commits it cites do exist in git. This is a documentation omission only, and the code and tests it describes exist.

To accept the double-submit deviation instead of fixing it, add to this file's frontmatter:

```yaml
overrides:
  - must_have: "The Create button is disabled while a create request is in flight, so a double-click produces exactly one session"
    reason: "Duplicate orphan sessions are harmless for v1; fix deferred"
    accepted_by: "{name}"
    accepted_at: "{ISO timestamp}"
```

---

_Verified: 2026-10-22_
_Verifier: Claude (gsd-verifier)_
