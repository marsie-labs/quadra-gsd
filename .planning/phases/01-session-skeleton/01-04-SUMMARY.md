---
phase: 01-session-skeleton
plan: 04
subsystem: infra
tags: [supabase-realtime, realtime-py, postgres-changes, startup-check, tdd, pytest]

requires:
  - phase: 01-session-skeleton
    provides: "Repository/connect, Settings.realtime_key(), hosted schema with realtime_probe in the supabase_realtime publication (plans 01-01, 01-02)"
provides:
  - "app.realtime.hub.RealtimeHub: one AsyncRealtimeClient, one channel (quadra-db), nonce-matched probe, run_startup_check(strict|warn|off), start/verify_roundtrip/stop/status"
  - "RealtimeCheckError with stage connect / subscribe / probe-write / no-event and the SUPABASE_REALTIME_KEY fix hint; keys and apikey= values sanitized"
  - "Repository.upsert_probe(nonce) writing realtime_probe id=1"
  - "Live proof that hosted Realtime accepts the sb_secret_ key (Open Question 1 / A1 settled)"
affects: [01-05, phase-02-realtime-cards]

plan_head_before: 27db8e703dfea6c8d0f1a0ac83831940d54e08d4
plan_head_after: 3677d6a6ab17d9263a39711b1140f54857a9487a

actuals:
  tokens: 4300
  tasks: 1
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Hub is the only Realtime owner; all postgres_changes bindings are added in _build_channel() before the single subscribe()"
    - "Postgres Changes callbacks are plain def (called synchronously in the socket loop) and only resolve a future"
    - "Startup success is proven only by an event carrying this run's random nonce; SUBSCRIBED alone never verifies"
    - "Every stored or logged error passes through _sanitize (key and apikey= masked); failures re-raised with 'from None'"

key-files:
  created:
    - app/realtime/__init__.py
    - app/realtime/hub.py
    - tests/unit/test_hub_dispatch.py
    - tests/integration/test_realtime_probe.py
  modified:
    - app/db/repository.py

key-decisions:
  - "Hosted Realtime accepts the sb_secret_ key for this project; SUPABASE_REALTIME_KEY (legacy JWT) is NOT needed and stays an optional override"
  - "Strict mode closes the half-started client (best-effort stop) before raising, so a failed boot leaves no live socket"
  - "Failures are re-raised with 'from None' so the original exception text (which can embed the URL) never appears in a traceback"

requirements-completed: [QUAL-04]

coverage:
  - id: D1
    description: "A change to realtime_probe reaches the Python server through hosted Supabase Realtime; the hub reports verified with a measured latency only after the nonce-matching event arrives"
    requirement: QUAL-04
    verification:
      - kind: integration
        ref: "tests/integration/test_realtime_probe.py#test_probe_roundtrip_via_hub"
        status: pass
    human_judgment: false
  - id: D2
    description: "A SUBSCRIBED channel alone or another run's nonce never verifies; with no matching event the check fails at stage no-event after at least two probe writes"
    requirement: QUAL-04
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_dispatch.py#test_non_matching_nonce_leaves_waiter_pending, #test_verify_roundtrip_times_out_with_no_event_after_resends, #test_subscribed_alone_never_verifies"
        status: pass
    human_judgment: false
  - id: D3
    description: "Broken Realtime setup never passes silently: strict raises a staged RealtimeCheckError naming SUPABASE_REALTIME_KEY, warn records failed with one ERROR log, off reports disabled without connecting"
    requirement: QUAL-04
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_dispatch.py#test_strict_check_failure_raises_with_stage_and_fix, #test_warn_check_failure_records_failed_without_key, #test_off_mode_is_disabled_without_connecting"
        status: pass
    human_judgment: false
  - id: D4
    description: "Neither the secret key, the Realtime key nor an apikey= fragment appears in hub.error, the raised error or the log records"
    requirement: QUAL-04
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_dispatch.py#test_warn_check_failure_records_failed_without_key, #test_probe_write_failure_is_staged"
        status: pass
      - kind: other
        ref: "live negative control with a garbage sb_secret_ key: stage connect (HTTP 401), key not in the error"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-22
status: complete
---

# Phase 1 Plan 04: Realtime Hub Summary

**RealtimeHub with a nonce-matched Postgres Changes round trip, proven live: hosted Supabase Realtime accepts the `sb_secret_` key (no legacy JWT needed) and delivers the probe event in 0.4 to 1.3 s.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-22T21:35:00Z
- **Completed:** 2026-10-22T21:41:00Z
- **Tasks:** 1 (TDD: RED + GREEN, no REFACTOR needed)
- **Files modified:** 5 (4 created, 1 modified)

## Realtime key outcome (copy into README `## Realtime key` in 01-05)

- **Key that worked:** the `sb_secret_...` key (SUPABASE_SECRET_KEY). `SUPABASE_REALTIME_KEY` was unset (`realtime_key_override_set: False`, effective key prefix `sb_secret_`). The Open Question 1 / A1 fallback was **not** needed. No auth gate was hit.
- **Measured probe latency (write via PostgREST to event received by the server), hosted project, 4 successful runs:** 361 ms, 634 ms and 1266 ms in a scratch loop of three fresh hubs, plus the pytest run (whole test 5.1 s including client setup and hub connect). Expect roughly 0.4 to 1.3 s.
- **Exact success log line:** `Realtime startup check verified: DB change event received in 361 ms` (logger `app.realtime.hub`, INFO; the number varies per run).
- **Stage failures before the fix:** none. The first live run passed at the first attempt (connect, subscribe and the first probe write all succeeded; no re-write was needed to catch the event, so Pitfall 5's re-upsert loop was not exercised live).
- **Negative control (live):** a garbage `sb_secret_xxx...` key makes the hub fail at stage `connect` with `InvalidStatus: server rejected WebSocket connection: HTTP 401`. The garbage key text does not appear in the error. This shows a wrong key is rejected loudly by hosted Realtime and the check cannot pass by accident.

## Accomplishments

- `RealtimeHub` owns the single Realtime client and channel; `_build_channel()` is the one place bindings are added (Phase 2 adds cards/workspaces there).
- `verify_roundtrip` writes a probe with a random nonce and returns latency only when the matching event arrives; it re-writes every `resend_every` seconds up to `timeout`, never reads rows back.
- `run_startup_check` implements strict (raise), warn (single ERROR log, state failed) and off (disabled, no connection); only the nonce-matched path can set `verified`.
- `Repository.upsert_probe` added; `create_session` / `get_session` untouched.

## Task Commits

1. **Task 1 RED:** `b99e193` (test) - 12 hub tests plus a signature-only `hub.py` stub; result 11 failed, 1 passed
2. **Task 1 GREEN:** `3677d6a` (feat) - hub implementation, `upsert_probe`, live integration test

**Plan metadata:** recorded in the following docs commit.

## TDD Gate Compliance

- RED commit `test(01-04)`: b99e193; GREEN commit `feat(01-04)`: 3677d6a. REFACTOR: none (ruff format only, folded into GREEN).
- **RED evidence:** `uv run pytest tests/unit/test_hub_dispatch.py -q` gave `11 failed, 1 passed`. The 11 failures are `NotImplementedError` raised from the stub's methods when the target tests call them (for example `test_status_has_exactly_four_keys` fails at `hub.status()`), not syntax, import or collection errors. The 1 pass is `test_on_probe_is_plain_def`, which only inspects that the stub's `_on_probe` is a plain def.
- **Semantic assessment (honest caveat):** every test executed and failed because the behavior is absent. However the failure mode is `NotImplementedError` from a stub rather than an assertion on the planned value, because the module did not exist and a missing import would have been a load failure. This is weaker than assertion-level RED. The plan is `type: execute`, not `type: tdd`, so `gsd_run check tdd-red-evidence` was not required and was not run.

## Files Created/Modified

- `app/realtime/__init__.py` - package marker
- `app/realtime/hub.py` - RealtimeHub, RealtimeCheckError, CHANNEL_TOPIC, StartupStage, log hygiene at import
- `app/db/repository.py` - `upsert_probe(nonce)`
- `tests/unit/test_hub_dispatch.py` - 12 offline tests (9 plan-named behaviors parametrized to 12, plus `test_probe_write_failure_is_staged` and `test_subscribed_alone_never_verifies`)
- `tests/integration/test_realtime_probe.py` - `test_probe_roundtrip_via_hub` (01-05 appends the app-startup test)

## Decisions Made

- Hosted Realtime accepts `sb_secret_`; keep `SUPABASE_REALTIME_KEY` as an optional override only. The README should tell users to set it only if the startup check fails at connect with HTTP 401/403.
- Strict mode calls `stop()` before raising so the half-open client is closed.
- Raise with `from None` after sanitizing, because `websockets` exceptions can embed the URL (with `?apikey=`) and a chained traceback would print it.

## Deviations from Plan

### Auto-fixed / additive

**1. [Rule 2 - Missing critical] Two extra tests beyond the nine named in the plan**
- **Found during:** Task 1 (RED design)
- **Issue:** The truths "a SUBSCRIBED channel alone never verifies" and "probe-write stage" were not directly covered by a named test.
- **Fix:** Added `test_subscribed_alone_never_verifies` and `test_probe_write_failure_is_staged`. The plan's five edge tests keep their exact names and select 5 passed.
- **Files modified:** tests/unit/test_hub_dispatch.py
- **Committed in:** b99e193

**2. [Rule 2 - Missing critical] Strict mode closes the client before raising**
- **Found during:** Task 1 (GREEN)
- **Issue:** A strict failure after a successful connect (for example no-event) would leave a live socket and listen/heartbeat tasks behind the aborting lifespan.
- **Fix:** `run_startup_check` awaits `stop()` (exception-safe) before re-raising in strict mode.
- **Committed in:** 3677d6a

---

**Total deviations:** 2 additive (both Rule 2). **Impact on plan:** none on the contract; the hub API for 01-05 is exactly as specified.

## Issues Encountered

- The realtime-py library itself logs `ERROR Connection attempt failed: ...` once per retry (5x) and a final `Connection failed permanently` line when connect fails, on the `realtime._async.client` logger. These lines contain the HTTP status only (verified live with a bad key: no key or URL). In `warn` mode the app log will therefore show these library ERROR lines in addition to the hub's single ERROR record. Not a leak, only noise; 01-05's console re-check (T-01-24) should expect them.
- `connect()` on a bad key takes about 15 s (5 attempts with 1/2/4/8 s backoff) before strict raises; that is the bounded connect stage (T-01-16).

## Known Stubs

None. (The RED-commit stub in `hub.py` was fully replaced in GREEN.)

## Threat Flags

None. The only new outbound surface is the already-planned WSS connection to the project's Realtime endpoint; no new endpoints, auth paths or schema changes. Mitigations T-01-14 (sanitized errors, loggers held at INFO, no URL/key logging, grep gate returns 0), T-01-15 (nonce-only verified, two unit tests) and T-01-16 (bounded connect/subscribe/probe waits) are implemented and tested.

## User Setup Required

None. `.env` already worked with the secret key alone.

## Next Phase Readiness

- 01-05 can call `RealtimeHub(settings.supabase_url, settings.realtime_key())`, `await hub.run_startup_check(settings.realtime_check, repo.upsert_probe)`, `hub.status()` for `/healthz`, and `await hub.stop()` on shutdown.
- Phase 2 note (carry-over from Pitfall 12): secret-key Realtime connections are capped at 24 h, and the subscribe state callback fires again on re-join; Phase 2 must resync there. The hub currently ignores post-startup state notifications.
- The hosted `realtime_probe` row (id=1) persists after tests by design (single upserted row).

## Self-Check: PASSED

- Files exist: app/realtime/__init__.py, app/realtime/hub.py, tests/unit/test_hub_dispatch.py, tests/integration/test_realtime_probe.py (all FOUND); app/db/repository.py contains `upsert_probe`.
- Commits b99e193 and 3677d6a are ancestors of HEAD.
- `uv run pytest -q`: 50 passed; `-m integration`: 11 passed; ruff check and format clean; five edge tests: 5 passed; log-hygiene grep prints 0.

---
*Phase: 01-session-skeleton*
*Completed: 2026-10-22*
