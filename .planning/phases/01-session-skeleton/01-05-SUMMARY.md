---
phase: 01-session-skeleton
plan: 05
subsystem: infra
tags: [fastapi, nicegui, uvicorn, lifespan, healthz, supabase-realtime, readme, subprocess-test]

requires:
  - phase: 01-session-skeleton
    provides: "Repository/connect, SessionService, deps.Services, register_pages, Settings (01-01..01-03); RealtimeHub nonce-matched startup check (01-04)"
provides:
  - "app.main.create_app(): lifespan wiring client -> services -> Realtime hub startup check, /healthz router registered before ui.run_with, 1-year NiceGUI session cookie"
  - "app.main.health_router: GET /healthz -> {status, realtime{state, stage, latency_ms, error}}"
  - "app.__main__.main(): single-worker launcher (uvicorn.run(create_app, factory=True, workers=1))"
  - "README.md: setup, migrations, single-worker run, startup check, Realtime key outcome, tests, layout"
  - "Real-server subprocess proof: verified startup check, cookie Max-Age, no key in the console"
affects: [phase-02-realtime-cards, phase-05-agent-results-endpoint]

plan_head_before: 969133e80c46d1578d9a04eade056f3c6c4c921c
plan_head_after: 8d764482492a867b5049dc467794a4cbb84a258d

actuals:
  tokens: 5000
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Composition root: every plain FastAPI route/router is registered before ui.run_with, which is the LAST call (NiceGUI mounts at / and shadows later routes)"
    - "Lifespan owns resource lifetime: connect -> services -> hub check; finally stops hub, clears deps.services, closes the PostgREST client"
    - "Health payload is a fixed four-key realtime dict from hub.status(); no settings, URLs or keys"
    - "Subprocess integration test writes the child's console to a file (no pipe deadlock) and asserts on the whole log"

key-files:
  created:
    - app/main.py
    - app/__main__.py
    - tests/unit/test_app_factory.py
    - README.md
  modified:
    - tests/integration/test_realtime_probe.py

key-decisions:
  - "Launcher hard-codes workers=1 and never reads it from env (NiceGUI client state and the in-process hub need one process)"
  - "Health route and launcher are unit-tested without calling create_app() in-process, because it mutates NiceGUI globals shared with the user-fixture tests; the real create_app() is exercised only by the subprocess integration test"
  - "Strict-mode failure is surfaced by the lifespan raising RealtimeCheckError from run_startup_check, which aborts startup; the finally block still stops the hub and closes the client"

patterns-established:
  - "Pitfall 1 ordering gate: awk check that include_router( precedes ui.run_with( in app/main.py"
  - "No-polling gate: no ui.timer( anywhere under app/; the only repeated request is the test's startup readiness probe"

requirements-completed: [QUAL-04, IDEN-02]

coverage:
  - id: D1
    description: "`uv run python -m app` starts one uvicorn worker serving the NiceGUI pages plus GET /healthz, and the launcher passes create_app, factory=True, workers=1 and the configured port"
    requirement: QUAL-04
    verification:
      - kind: unit
        ref: "tests/unit/test_app_factory.py#test_launcher_runs_uvicorn_once_with_one_worker"
        status: pass
      - kind: integration
        ref: "tests/integration/test_realtime_probe.py#test_app_starts_and_proves_realtime"
        status: pass
    human_judgment: false
  - id: D2
    description: "The server's lifespan runs the Realtime round-trip check before serving; the real subprocess logs 'Realtime startup check verified' and /healthz reports realtime.state verified with status ok"
    requirement: QUAL-04
    verification:
      - kind: integration
        ref: "tests/integration/test_realtime_probe.py#test_app_starts_and_proves_realtime"
        status: pass
    human_judgment: false
  - id: D3
    description: "/healthz returns {status, realtime{state, stage, latency_ms, error}} with ok for verified/disabled and degraded for failed/pending, exposing only those keys"
    requirement: QUAL-04
    verification:
      - kind: unit
        ref: "tests/unit/test_app_factory.py#test_healthz_verified_is_ok, #test_healthz_failed_is_degraded, #test_healthz_without_hub_is_pending_and_degraded, #test_healthz_disabled_is_ok, #test_healthz_exposes_only_the_documented_keys"
        status: pass
    human_judgment: false
  - id: D4
    description: "The NiceGUI session cookie is issued with Max-Age=31536000 so a display name survives beyond Starlette's 14-day default"
    requirement: IDEN-02
    verification:
      - kind: integration
        ref: "tests/integration/test_realtime_probe.py#test_app_starts_and_proves_realtime (set-cookie contains max-age=31536000)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Neither the secret key, the Realtime key nor an apikey= fragment appears in the running server's console output"
    requirement: QUAL-04
    verification:
      - kind: integration
        ref: "tests/integration/test_realtime_probe.py#test_app_starts_and_proves_realtime (log assertions)"
        status: pass
    human_judgment: false
  - id: D6
    description: "The app never polls the database: no ui.timer under app/, no loop in the launcher, uvicorn.run called once, route-order gate passes"
    requirement: QUAL-04
    verification:
      - kind: other
        ref: "test -d app && ! grep -rnE 'ui\\.timer\\(' app; awk include_router-before-run_with gate on app/main.py"
        status: pass
    human_judgment: false
  - id: D7
    description: "README.md lets a developer set env vars, push migrations, start the single-worker app and read the startup check result, and records which Realtime key worked"
    requirement: QUAL-04
    verification:
      - kind: other
        ref: "grep heading/fact gate and key-shape gate on README.md"
        status: pass
    human_judgment: true
    rationale: "Whether the README is followable from a fresh clone with nothing else needs a human to walk through it (plan Task 2 human-check, VALIDATION manual-only row)."

duration: 4min
completed: 2026-10-22
status: complete
---

# Phase 1 Plan 05: Composition Root, Launcher and README Summary

**Runnable single-worker Quadra: `create_app()` lifespan wires the Supabase client, services and RealtimeHub startup check, serves `/healthz` and NiceGUI from one FastAPI app with a 1-year session cookie, proven by a real-subprocess test and documented in a README.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-22T21:41:32Z
- **Completed:** 2026-10-22T21:43:44Z (task commits; metadata commit follows)
- **Tasks:** 2
- **Files modified:** 5 (4 created, 1 modified)

## Evidence for the plan's output spec

- **Exact startup log line seen:** `Realtime startup check verified: DB change event received in 348 ms` (logger `app.realtime.hub`, INFO; observed in a manual background run and asserted as the substring `Realtime startup check verified` in the subprocess test). The manual run's `/healthz` returned `{"status":"ok","realtime":{"state":"verified","stage":null,"latency_ms":348.05...,"error":null}}`. The console also showed `INFO quadra: Quadra starting on http://localhost:8080 (single worker)`.
- **README `## Realtime key` outcome (copied from 01-04):** hosted Realtime accepts the `sb_secret_` key; `SUPABASE_REALTIME_KEY` was not needed and stays an optional override, to be set only if the check fails at stage `connect` with HTTP 401/403. Measured latency roughly 0.35 to 1.3 s. No key value is in the README.
- **Did any startup stage fail before the fix:** no. The real server passed the strict check on the first run, and the test passed on its first run.

## Accomplishments

- `app/main.py`: `health_router` (`GET /healthz`), `make_lifespan(settings)` (connect, `Repository`, `deps.services`, `RealtimeHub`, `run_startup_check(settings.realtime_check, repo.upsert_probe)`, cleanup in `finally`) and `create_app()` which registers the router and pages and calls `ui.run_with(... session_middleware_kwargs={"max_age": 365 * 24 * 3600})` last.
- `app/__main__.py`: `main()` logs the start line and calls `uvicorn.run(create_app, factory=True, host, port, workers=1)` exactly once, no loop.
- Subprocess integration test starts `python -m app` on a free port with `REALTIME_CHECK=strict`, waits for `/healthz` (test-harness readiness probe, commented as such), asserts `verified`/`ok`, `GET /` 200 with `max-age=31536000`, and that the captured console has the success line and neither key nor `apikey=`.
- README with the eight required level-2 sections, every command one that was run in this phase.

## Task Commits

1. **Task 1 RED:** `7d2feb2` (test) - 9 tests failing on assertions (404 vs 200 for `/healthz`, `uvicorn.run` never called), with signature-only stubs for `app/main.py` and `app/__main__.py`
2. **Task 1 GREEN:** `d626f64` (feat) - composition root, `/healthz`, launcher, appended subprocess integration test
3. **Task 2:** `8d76448` (docs) - README.md

**Plan metadata:** recorded in the following docs commit.

## TDD Gate Compliance

The plan is `type: execute` with a `tdd="true"` task, so `gsd_run check tdd-red-evidence` was not required and was not run.

- RED commit `test(01-05)`: 7d2feb2; GREEN commit `feat(01-05)`: d626f64. REFACTOR: none.
- **RED evidence:** `uv run pytest tests/unit/test_app_factory.py -q` gave `9 failed`. Observed assertion-level failures: `assert 0 == 1` (`len(calls)`, `uvicorn.run` was never called by the stub launcher) and `assert 404 == 200` (the empty stub router has no `/healthz`); the remaining health tests failed with `KeyError: 'realtime'` on the 404 body.
- **Semantic assessment:** every target test executed and failed because the behavior is absent, not from syntax, import, collection or fixture faults. The failures come from the planned behavior being absent, though the stubs made the import succeed, so the health tests fail at the first status/key access rather than on each distinct planned value. This is assertion-level for the launcher and the status code, and a body-shape KeyError for the rest.
- The integration test was appended in the GREEN commit, not RED, because it needs the real app to exist and a hosted-Supabase run to be meaningful.

## Files Created/Modified

- `app/main.py` - `health_router`, `make_lifespan`, `create_app`
- `app/__main__.py` - single-worker launcher
- `tests/unit/test_app_factory.py` - launcher test (runpy with patched `uvicorn.run`) plus 5 health tests (one parametrized over 4 states)
- `tests/integration/test_realtime_probe.py` - appended `test_app_starts_and_proves_realtime` and two helpers
- `README.md` - setup, migrations, run, startup check, Realtime key, tests, layout

## Decisions Made

- The launcher test uses `runpy.run_module("app", run_name="__main__")` with env vars set and `uvicorn.run` patched, so it needs no network and does not call `create_app()` in-process.
- Cleanup order in the lifespan `finally` is hub stop, then `deps.services = None`, then PostgREST client close, so a strict-mode failure leaves no live socket or client.

## Deviations from Plan

None - plan executed exactly as written.

Minor, non-deviating choices: the RED commit used stub modules (`health_router` empty, `main()` a no-op) so the tests fail on assertions instead of at import, mirroring 01-04's approach; a helper `_sanitized_log` redacts both keys from the log tail used in the test's failure message so a failing run cannot print a key.

## Issues Encountered

None. One local slip: a `sed -i` call for a README wording tweak failed on macOS BSD sed and the same edit was applied with a Python replace instead. No code or behavior was affected.

## Authentication Gates

None. No schema change was made and no hosted-DB write other than the probe-row upsert performed by the startup check itself.

## Known Stubs

None.

## Threat Flags

None. `/healthz` is the only new endpoint and is already covered by T-01-17 (fixed four-key payload, unit-pinned). T-01-24 (keys in the console) is covered by the subprocess test; T-01-25 (key in README) by the key-shape gate.

## User Setup Required

None - no external service configuration beyond the existing `.env` documented in the README.

## Next Phase Readiness

- The app is runnable and observable: `uv run python -m app` verifies Realtime at startup, `/healthz` reports it.
- Phase 2 can add its postgres_changes bindings in `RealtimeHub._build_channel()` and add routers to `create_app()` before the `ui.run_with` call.
- Open for a human: follow the README from a fresh terminal (plan Task 2 human-check; VALIDATION manual-only row "README reproduces setup from clean clone"), and the two-browser name check from VALIDATION.

## Verification Results

- `uv run pytest -q`: 59 passed, 12 deselected
- `uv run pytest -m integration -q`: 12 passed
- `uv run pytest -m integration tests/integration/test_realtime_probe.py -q -rs`: 2 passed, 0 skipped
- awk route-order gate: pass; `! grep -rnE 'ui\.timer\(' app`: pass; `workers=(settings|os.environ|int()` count 0; launcher loop-header count 0
- README heading/fact gate and key-shape gate: pass
- `uv run ruff check .` and `uv run ruff format --check .`: clean

## Self-Check: PASSED

- FOUND: app/main.py, app/__main__.py, tests/unit/test_app_factory.py, README.md
- FOUND commits: 7d2feb2, d626f64, 8d76448 (all ancestors of HEAD)

---
*Phase: 01-session-skeleton*
*Completed: 2026-10-22*
