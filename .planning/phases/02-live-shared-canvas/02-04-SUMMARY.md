---
phase: 02-live-shared-canvas
plan: 04
subsystem: live-sync
tags: [nicegui, supabase-realtime, resync, snapshot-buffering, http-503, pytest, tdd]
status: complete

requires:
  - phase: 02-live-shared-canvas
    provides: "02-03 CanvasView.apply_card/remove_card projection, hub id-only DELETE routing; 02-01/02 hub registry, fakes"
provides:
  - "CanvasView snapshot protocol: begin_loading, load_snapshot, async single-flight resync, plain-def request_resync"
  - "Canvas page read-then-render flow with 503 'Temporarily unavailable' on database failure (closes Phase 1 WR-05)"
  - "on_connect reconnect resync (every handshake after the first)"
  - "FakeRepository list_calls, list_gate, fail_next_list_codes, fail_next_get_codes, soft_delete_card"
  - "Live server-restart proof against hosted Supabase with the real app as a subprocess"
affects: [02-05-realtime-recovery, 03-edit-delete-move-ui]

actuals:
  tokens: 7000
  tasks: 2
  commits: 3

plan_head_before: 6ddd3423859699e718c4d5bddb51ab35bea8c21a
plan_head_after: cc97363703e089e313fe4d429efa3be5c8e07a81
commits: 3

tech-stack:
  added: []
  patterns:
    - "Loading counter (_reads_in_flight) instead of a boolean: page-open read and resync reads can overlap, events replay only after the last outstanding read"
    - "apply_card/remove_card are buffering wrappers over _apply/_remove projections; snapshot and replay call the projections directly"
    - "Background UI work uses 'with self._root:' for ui.notify; every post-await step checks the root is not deleted"
    - "Log hygiene in integration tests: assert a boolean, print only a sanitized tail"

key-files:
  created:
    - tests/ui/test_canvas_recovery.py
    - tests/integration/test_restart_recovery.py
  modified:
    - app/ui/canvas_view.py
    - app/ui/canvas_page.py
    - tests/ui/fakes.py

key-decisions:
  - "Snapshot is authoritative: load_snapshot drops and re-renders any card whose state differs (bypassing the stale guard), leaves identical cards untouched, then replays the buffered events through the normal stale guard"
  - "A read counter replaces a loading boolean so an hub-initiated request_resync during page open cannot make events apply live while a read is outstanding"
  - "The page unregisters its canvas on card-read failure and also registers on_delete before the read, so no exit path leaves a dead listener"

patterns-established:
  - "Reconnect simulation: replay user.client.connect_handlers via safe_invoke after user.open (open already ran the first handshake)"
  - "_settle(): harness wait for background tasks named 'canvas resync ...' to finish"

requirements-completed: [SYNC-04, SYNC-02]

coverage:
  - id: D1
    description: "A reconnecting browser reloads cards from the database (added and soft-deleted while away), the first handshake reads nothing extra, and a reopened tab shows cards written meanwhile"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_reconnect_handshake_resyncs_from_db"
        status: pass
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_first_handshake_does_not_read_again"
        status: pass
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_reopen_after_tab_closed_shows_cards_written_meanwhile"
        status: pass
    human_judgment: true
    rationale: "The fixture has no real socket; a real browser going offline and back online is the end-of-phase human check"
  - id: D2
    description: "Events during a snapshot read are buffered and replayed; concurrent resyncs coalesce; request_resync reloads from the database"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_event_during_resync_beats_older_snapshot"
        status: pass
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_resync_requests_coalesce"
        status: pass
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_request_resync_reloads_from_db"
        status: pass
    human_judgment: false
  - id: D3
    description: "A failed resync keeps the cards, shows 'Could not refresh the cards...', logs one WARNING, and later live events still apply"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_resync_failure_keeps_cards_and_warns"
        status: pass
    human_judgment: false
  - id: D4
    description: "A database failure on page open answers 503 'Temporarily unavailable' (never 'Session not found') and leaves no hub registration"
    requirement: SYNC-04
    verification:
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_session_read_failure_returns_503"
        status: pass
      - kind: unit
        ref: "tests/ui/test_canvas_recovery.py#test_card_read_failure_returns_503_and_unregisters"
        status: pass
    human_judgment: false
  - id: D5
    description: "The real app restarted as a new process, against hosted Supabase, shows a card written while no server ran; logs hold no key material"
    requirement: SYNC-04
    verification:
      - kind: integration
        ref: "tests/integration/test_restart_recovery.py#test_server_restart_shows_cards_added_while_down"
        status: pass
    human_judgment: true
    rationale: "Automation drives the app over HTTP; two real browsers surviving a Ctrl-C restart is the end-of-phase human check"
  - id: D6
    description: "Card state is read only on page open, reconnect handshake and explicit request_resync; no timer-driven refresh"
    requirement: SYNC-02
    verification:
      - kind: command
        ref: "test -d app && ! grep -rnE 'ui\\.timer\\(' app"
        status: pass
    human_judgment: false
---

# Phase 2 Plan 04: Reconnect and Restart Recovery Summary

**Canvases now catch up from the database on page open, on every browser reconnect handshake and on `request_resync()`, through a buffered snapshot protocol that never loses a newer event; a database blip answers 503 instead of "Session not found"; and a live test restarts the real app against hosted Supabase and finds a card written while it was down.**

## Performance

- **Duration:** about 7 min (2026-10-23, 11:25Z to 11:32Z, approximate; start time was not captured)
- **Tasks:** 2 (Task 1 TDD)
- **Files:** 2 created, 3 modified

## Accomplishments

- `CanvasView` snapshot protocol. While a read is in flight the view is loading and buffers `apply_card`/`remove_card`; `load_snapshot` makes the view show exactly the snapshot (unchanged cards untouched), then replays the buffer through the normal stale guard.
- `resync()` is single-flight: concurrent requests set one rerun flag, so at most one read runs and one follows. A failed read logs one WARNING (exception class only), keeps the cards, replays the buffer onto the current state and shows "Could not refresh the cards. Reload the page to try again."
- `request_resync()` is a plain `def` that schedules `resync()` via `background_tasks.create`; 02-05's hub calls it after Realtime recovery.
- Canvas page is read-then-render: session read, register the loading canvas, card read, then header/banner/build/snapshot. Any read failure renders the 503 page (fixed text) and unregisters the canvas. `client.on_connect` ignores the first handshake and calls `request_resync()` on every later one.
- Live proof (SYNC-04): the real app runs twice as a subprocess; card B is written between runs while no server runs; the second process serves both cards, and neither log contains key material.

## TDD record

RED commit `e03ffe7` (`test(02-04)`), GREEN commit `ae80309` (`feat(02-04)`). Tests RED before implementation, each failing on the planned behavior (semantic assessment: no import or fixture errors; the failures were a missing `request_resync` attribute, a card that never arrived after a replayed handshake, a second `list_calls` that never happened, and an unhandled `APIError` where a 503 was expected):

- `test_reconnect_handshake_resyncs_from_db` (no resync on handshake)
- `test_event_during_resync_beats_older_snapshot` (no resync read: `list_calls` stayed 1)
- `test_resync_requests_coalesce` (`AttributeError: request_resync`)
- `test_resync_failure_keeps_cards_and_warns` (no notification, no resync)
- `test_session_read_failure_returns_503` (exception escaped as 500)
- `test_card_read_failure_returns_503_and_unregisters` (exception escaped as 500)
- `test_request_resync_reloads_from_db` (`AttributeError: request_resync`)

Already green at RED, kept as regression guards: `test_reopen_after_tab_closed_shows_cards_written_meanwhile` and `test_first_handshake_does_not_read_again` (baseline page open already read once).

No REFACTOR commit.

## Restart proof: boot times

`test_server_restart_shows_cards_added_while_down` prints the time from `Popen` to `/healthz` realtime `verified` for each process. Last run: **run 1 1.5 s, run 2 1.5 s**. The test passed in both of its runs in this session, 0 skipped. No `python -m app` process was left running.

## Task Commits

1. **Task 1 RED:** `e03ffe7` test(02-04): add failing tests for reconnect resync, buffering and 503 handling
2. **Task 1 GREEN:** `ae80309` feat(02-04): resync a reconnecting canvas from the database and answer 503 on read failure
3. **Task 2:** `cc97363` test(02-04): prove a restarted server shows cards written while it was down

## Verification

- `uv run pytest tests/ui/test_canvas_recovery.py -q`: 9 passed (tests/ui run three times in a row: 67 passed each, no flakes).
- `uv run pytest -q`: 164 passed, 21 deselected; `uv run ruff check .` and `uv run ruff format --check .` clean.
- `uv run pytest -m integration tests/integration/test_restart_recovery.py -q -rs`: 1 passed, 0 skipped.
- `test -d app && ! grep -rnE 'ui\.timer\(' app`: no matches. `request_resync` is not a coroutine function, `resync` is.
- Precondition (`test_realtime_probe.py -k app_starts`): 1 passed before Task 2.

## Deviations from Plan

None - plan executed exactly as written. Two small implementation choices go beyond the plan text without changing behavior: a read counter instead of a boolean (so a hub-initiated resync during page open stays safe), and `on_delete` registered before the card read rather than after (so a cancelled page load cannot leave a listener behind).

**Total deviations:** 0.

## Known Stubs

None.

## Threat Flags

None. T-02-18 through T-02-22 mitigations are implemented and tested as planned (buffer-and-replay, single-flight resync, class-name-only logging, 503 instead of 404, secrets asserted absent from both process logs). No packages installed; pyproject.toml and uv.lock unchanged. The restart test asserts on a boolean so a leak cannot echo the key through pytest's assertion rewriting.

## Issues Encountered

None open. End-of-phase human check from the plan is still pending: browser A offline about 10 s while B adds a card; stop and restart the server with a card inserted via the SQL editor meanwhile; `/healthz` shows realtime verified afterwards. A real browser reconnect cannot be exercised by the NiceGUI `user` fixture; the offline tests replay `connect_handlers`, the list `Client.handle_handshake` runs.

## Next Phase Readiness

Ready for 02-05: `CanvasView.request_resync()` exists for the hub's Realtime recovery to call on every registered canvas.

## Self-Check: PASSED

- Files present: app/ui/canvas_view.py, app/ui/canvas_page.py, tests/ui/fakes.py, tests/ui/test_canvas_recovery.py, tests/integration/test_restart_recovery.py
- Commits present: e03ffe7, ae80309, cc97363
