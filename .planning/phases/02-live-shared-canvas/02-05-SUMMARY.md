---
phase: 02-live-shared-canvas
plan: 05
subsystem: realtime-recovery
tags: [supabase-realtime, realtime-py, recovery, supervisor, backoff, healthz, readme, pytest, tdd]
status: complete

requires:
  - phase: 02-live-shared-canvas
    provides: "02-04 CanvasView.request_resync(); 02-01..03 hub registry, probe, cards fan-out"
provides:
  - "Hub post-startup channel state handling (_on_channel_state): re-join re-verify, CHANNEL_ERROR/TIMED_OUT/CLOSED recovery"
  - "Single-flight _recover with RECOVERY_BACKOFF (1, 2, 4, 8, 16, 30 s, then 30 s), nonce re-probe, then request_resync on every canvas"
  - "Connection supervisor (_supervise/_start_supervisor) that rebuilds a silently closed socket"
  - "Bounded probe writes (WR-04) and warn-mode self-healing (IN-03)"
  - "healthz realtime state 'reconnecting' (status degraded)"
  - "Live dropped-socket recovery proof against hosted Supabase"
  - "README Phase 2 documentation"
affects: [03-edit-delete-move-ui, 04-close-and-agent-snapshot]

actuals:
  tokens: 10745
  tasks: 3
  commits: 5

plan_head_before: 2bcfae4e6ac8ced32631d06c2d6d89e69866a79d
plan_head_after: f1139f614df9a9ec3a1a7a1ee6ae33206c28de40
commits: 5

tech-stack:
  added: []
  patterns:
    - "Recovery is reaction-only: every step follows a Realtime state change or an ended listen task; no timers re-read the database"
    - "Injectable self._sleep and self._new_client let recovery run offline in tests"
    - "Supervisor waits on the client's private _listen_task with asyncio.wait; a replaced task means the library reconnected itself"
    - "Hub tasks (recovery, re-verify, supervisor) are cancelled and awaited in stop()"

key-files:
  created:
    - tests/unit/test_hub_recovery.py
    - tests/integration/test_realtime_recovery.py
  modified:
    - app/realtime/hub.py
    - tests/unit/test_hub_dispatch.py
    - README.md

key-decisions:
  - "Canvases resync only after the nonce probe proves change data capture again, so no event can fall between the snapshot read and the first live event"
  - "The supervisor depends on realtime 2.33's private AsyncRealtimeClient._listen_task, pinned by uv.lock and guarded by test_listen_task_attribute_exists"
  - "Recovery cancels the old supervisor and re-verify task at the start of every attempt, then starts a fresh supervisor only after a verified rebuild"
  - "A non-RealtimeCheckError failure during recovery is stored as stage 'connect' with the exception class name only"

patterns-established:
  - "Test rig: FakeRt with a controllable _listen_task future plus recorders for start/verify/sleep, assigned directly on the hub"
  - "Live recovery test gates hub.start behind an asyncio.Event so a card can be written while no socket exists"

requirements-completed: [SYNC-04, SYNC-01, SYNC-02, QUAL-02]

coverage:
  - id: D1
    description: "A channel error, timeout or close starts exactly one recovery that rebuilds client and channel, re-proves events with the nonce probe, then resyncs every canvas"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_channel_error_starts_one_recovery"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_rejoin_subscribed_reverifies_then_resyncs"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_failed_reverify_after_rejoin_starts_recovery"
        status: pass
    human_judgment: false
  - id: D2
    description: "Recovery backs off 1, 2, 4, 8, 16, 30 then 30 s, never leaks keys, and stop() ends it"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_recovery_backoff_sequence"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_recovery_logs_and_errors_are_sanitized"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_stop_cancels_recovery"
        status: pass
    human_judgment: false
  - id: D3
    description: "A silently closed socket (normal close, 24 h cap) is noticed and rebuilt; a library reconnect is left alone; one supervisor at a time"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_closed_socket_triggers_recovery"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_library_reconnect_does_not_rebuild"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_supervisor_started_after_verified_startup_and_recovery"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_listen_task_attribute_exists"
        status: pass
    human_judgment: false
  - id: D4
    description: "Warn-mode startup failure recovers to verified (IN-03); probe writes are bounded (WR-04); /healthz shows reconnecting as degraded"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_warn_mode_failure_recovers_to_verified"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_probe_write_is_bounded"
        status: pass
      - kind: unit
        ref: "tests/unit/test_hub_recovery.py#test_reconnecting_state_is_degraded_on_healthz"
        status: pass
    human_judgment: false
  - id: D5
    description: "Against hosted Supabase, a hub whose socket is closed rebuilds itself, the canvas picks up a card written during the outage, and new cards flow live again; logs hold no key material"
    requirement: SYNC-04
    verification:
      - kind: integration
        ref: "tests/integration/test_realtime_recovery.py#test_hub_recovers_from_dropped_socket_and_resyncs"
        status: pass
    human_judgment: false
  - id: D6
    description: "Recovery re-reads card state only in response to a detected loss or re-join, never on a timer"
    requirement: SYNC-02
    verification:
      - kind: command
        ref: "test -d app && ! grep -rnE 'ui\\.timer\\(' app"
        status: pass
    human_judgment: false
  - id: D7
    description: "README documents Phase 2: live cards, live updates with the SQL-editor demo, reconnects/restarts/recovery, the reconnecting state, REALTIME_CHECK=off, the second migration"
    requirement: QUAL-02
    verification:
      - kind: command
        ref: "grep README.md for '## Live cards', '## Reconnects and restarts', 'reconnecting', '20261023000000_author_nonblank.sql', 'REALTIME_CHECK=off'"
        status: pass
    human_judgment: true
    rationale: "Whether the documentation reads clearly to a new user is a human judgment"
---

# Phase 2 Plan 05: Realtime Recovery Summary

**The hub's Realtime subscription now heals itself: channel errors, library re-joins and silently closed sockets trigger a single-flight, capped-backoff rebuild that re-proves change data capture with the nonce probe and only then makes every open canvas resync from the database. A live test against hosted Supabase confirms it, and the README documents the whole of Phase 2.**

## Performance

- **Duration:** about 6 min (2026-10-23, 11:35Z to 11:41Z)
- **Tasks:** 3 (Tasks 1 and 2 TDD)
- **Files:** 2 created, 3 modified

## Accomplishments

- `RealtimeHub._on_channel_state` (plain def) is the one subscribe callback. During `start()` it resolves readiness; afterwards SUBSCRIBED means realtime-py re-joined (re-verify, then resync) and CHANNEL_ERROR, TIMED_OUT or CLOSED set `reconnecting` and start recovery.
- `_recover` is single-flight and loops until success or stop: close the old client, build a new one, `start()`, `verify_roundtrip()`, then `_resync_listeners()` and a fresh supervisor. Backoff delays are `RECOVERY_BACKOFF` (1, 2, 4, 8, 16, 30 s, then 30 s). Errors are sanitized and logged as warnings with the stage only.
- `_supervise` awaits the client's `_listen_task`. If it ended and was not replaced, the socket closed silently (normal close, 24 h cap) and recovery starts. If realtime-py replaced it, its own reconnect is in progress and the re-join arrives as SUBSCRIBED.
- Probe writes are wrapped in `asyncio.wait_for` (WR-04): a hung write fails at stage `probe-write`. A warn-mode startup failure schedules recovery instead of staying `failed` forever (IN-03).
- `stop()` cancels and awaits the supervisor, recovery and re-verify tasks, then closes the client.
- README gained `## Live cards`, `## Live updates` (with the three SQL-editor statements), `## Reconnects and restarts`, the second migration table with per-version repair commands, the `reconnecting` health state and the `REALTIME_CHECK=off` caveat. Phase 1 facts (`workers=1`, `## Startup Realtime check`) are kept.

## Live recovery timing

`test_hub_recovers_from_dropped_socket_and_resyncs` prints the time from opening the recovery gate to state `verified` with the canvas resynced. Observed: **1164 ms** (first run) and **986 ms** (second run). The test passed in the full live suite as well: `uv run pytest -m integration -q -rs` reports **22 passed, 0 skipped**. No `python -m app` process was left running.

## TDD record

Task 1: RED commit `ea92b2c`, GREEN commit `0dcf104`. The classifier (`gsd_run check tdd-red-evidence` on the JUnit report) returned `RED_EVIDENCE_OK` / `target_test_failed`. 9 of 10 tests failed before implementation, each on the planned behavior (semantic assessment: no import or collection errors; hooks were assigned directly so missing methods surfaced inside the test body):

- `test_rejoin_subscribed_reverifies_then_resyncs` (no `_on_channel_state`)
- `test_channel_error_starts_one_recovery` (no `_on_channel_state`)
- `test_recovery_backoff_sequence` (no recovery)
- `test_recovery_logs_and_errors_are_sanitized` (no recovery)
- `test_failed_reverify_after_rejoin_starts_recovery` (no `_on_channel_state`)
- `test_resync_isolated_per_listener` (no `_resync_listeners`)
- `test_warn_mode_failure_recovers_to_verified` (no `_recovery_task`; state stayed failed)
- `test_stop_cancels_recovery` (timed out waiting for a recovery that never started)
- `test_probe_write_is_bounded` (hung write never timed out; `wait_for` hit its 2 s guard)

`test_reconnecting_state_is_degraded_on_healthz` was already green at RED (the healthz mapping treats any state outside verified/disabled as degraded) and is kept as a regression guard.

Task 2: RED commit `928389a`, GREEN commit `3dfad61`. Classifier `RED_EVIDENCE_OK`. 4 of 5 tests failed before implementation:

- `test_closed_socket_triggers_recovery` (no recovery started)
- `test_library_reconnect_does_not_rebuild` (`_supervisor_task` missing)
- `test_supervisor_started_after_verified_startup_and_recovery` (`_supervisor_task` missing)
- `test_stop_ends_supervisor` (`_supervisor_task` missing)

`test_listen_task_attribute_exists` was green at RED by design (it pins the realtime 2.33 attribute). No REFACTOR commits. Task 3 is a normal task (live test plus docs): `f1139f6`.

## Private `_listen_task` dependency

The supervisor reads `AsyncRealtimeClient._listen_task`, a private attribute of realtime 2.33. It is pinned by `uv.lock` (no packages were installed in this plan) and guarded by `tests/unit/test_hub_recovery.py::test_listen_task_attribute_exists`, which fails loudly if an upgrade renames it. A code comment on `_supervise` records the dependency. If the attribute is missing at runtime, `getattr(..., None)` makes the supervisor treat it as a lost connection and start recovery rather than silently disabling it.

## Task Commits

1. **Task 1 RED:** `ea92b2c` test(02-05): add failing tests for hub channel-error recovery, re-join resync and bounded probe writes
2. **Task 1 GREEN:** `0dcf104` feat(02-05): hub heals a channel error or re-join, re-proves events, then resyncs canvases
3. **Task 2 RED:** `928389a` test(02-05): add failing tests for the silent-close supervisor
4. **Task 2 GREEN:** `3dfad61` feat(02-05): supervisor rebuilds a Realtime socket that closed silently
5. **Task 3:** `f1139f6` test(02-05): prove a dropped Realtime socket recovers and document Phase 2

## Verification

- `uv run pytest tests/unit/test_hub_recovery.py -q -W error::pytest.PytestUnraisableExceptionWarning`: 15 passed (run three more times in a row, no flakes).
- `uv run pytest -q`: 179 passed, 22 deselected; `uv run ruff check .` and `uv run ruff format --check .` clean.
- `uv run pytest -m integration -q -rs`: 22 passed, 0 skipped (includes `test_realtime_recovery.py`).
- Acceptance greps: `RECOVERY_BACKOFF`, `def _on_channel_state(`, `async def _recover(`, `def _schedule_recovery(`, `def _resync_listeners(`, `"reconnecting"`, `asyncio.wait_for(write_probe(`, `async def _supervise(`, `def _start_supervisor(`, `_listen_task` all present in `app/realtime/hub.py`. `_on_channel_state` is not a coroutine function. `grep -cE 'logger\.(error|exception)' app/realtime/hub.py` prints 1 (the warn-mode startup ERROR, as at baseline).
- `! grep -rnE 'ui\.timer\(' app`: no matches.
- README required strings present; `workers=1` and `## Startup Realtime check` kept.
- Precondition (`test_realtime_probe.py -k roundtrip_via_hub`): 1 passed before Task 3.

## Deviations from Plan

None - plan executed exactly as written. Small implementation choices beyond the plan text: `_recover` also cancels the old supervisor and any in-flight re-verify task at the start of each attempt (so neither watches or verifies a client that is about to be replaced), and the supervisor reads the finished listen task's exception once so asyncio logs no "never retrieved" noise (the exception text could carry the connection URL, so it is not logged).

**Total deviations:** 0.

## Known Stubs

None.

## Threat Flags

None. T-02-23 through T-02-28 mitigations are implemented and tested as planned: sanitized recovery errors (unit test plus the live test asserting no key or `apikey=` in captured logs), single-flight capped backoff, supervisor plus `reconnecting`/`degraded` visibility, task cancellation in `stop()`, bounded probe writes, and the attribute guard test. No packages installed; `pyproject.toml` and `uv.lock` unchanged.

## Issues Encountered

None open. The library's own error-reconnect path (ConnectionClosedError) is covered offline by the re-join unit tests, not live: the live test forces the normal-close path, as the plan flagged. The end-of-phase human checks from 02-03 and 02-04 (two real browsers, SQL editor, offline/online, Ctrl-C restart) remain pending for the phase verifier.

## Next Phase Readiness

Phase 2 plans are all executed. The hub can now be trusted to resync canvases after Realtime outages and the 24 h cap, so Phase 3 (edit, delete, move UI) and Phase 4 (close and agent snapshot) build on a self-healing subscription.

## Self-Check: PASSED

- Files present: app/realtime/hub.py, tests/unit/test_hub_recovery.py, tests/unit/test_hub_dispatch.py, tests/integration/test_realtime_recovery.py, README.md
- Commits present: ea92b2c, 0dcf104, 928389a, 3dfad61, f1139f6
