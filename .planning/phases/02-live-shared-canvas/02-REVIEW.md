---
phase: 02-live-shared-canvas
reviewed: 2026-10-23T00:00:00Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - README.md
  - app/db/repository.py
  - app/deps.py
  - app/main.py
  - app/models.py
  - app/realtime/hub.py
  - app/services/sessions.py
  - app/ui/canvas_page.py
  - app/ui/canvas_view.py
  - app/ui/identity.py
  - supabase/migrations/20261023000000_author_nonblank.sql
  - tests/conftest.py
  - tests/integration/test_card_author_check.py
  - tests/integration/test_card_storage.py
  - tests/integration/test_live_cards.py
  - tests/integration/test_realtime_recovery.py
  - tests/integration/test_restart_recovery.py
  - tests/ui/fakes.py
  - tests/ui/test_canvas_recovery.py
  - tests/ui/test_card_authoring.py
  - tests/ui/test_cards.py
  - tests/ui/test_live_projection.py
  - tests/unit/test_card_rules.py
  - tests/unit/test_hub_dispatch.py
  - tests/unit/test_hub_recovery.py
findings:
  critical: 0
  warning: 4
  info: 7
  total: 11
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-10-23
**Depth:** standard
**Files Reviewed:** 25
**Status:** issues_found

## Summary

The phase adds the live card canvas (CanvasView snapshot/buffer protocol), the hub's card fan-out, and the Realtime recovery machinery (single-flight rebuild, nonce re-proof, silent-close supervisor). The overall design is careful: user text is only rendered through `ui.label`, keys are sanitized out of logs and errors, writes are validated in the service before any repository call, and the supervisor logic was checked against the installed realtime-py 2.33 source (`_on_connect` cancels the running listen task and replaces it, so the "current is not task and not done" test is correct).

I found no security vulnerabilities and no data-loss defect. The four warnings are a state-machine hole in the canvas resync (a view can become permanently frozen), a cancellation-swallowing helper in the hub, a silent 1000-row truncation that the resync turns into card removal, and a latency-threshold test that will flake on a real network. The info items are dead or stale code, DB/service rule drift and test-double drift.

## Warnings

### WR-01: A resync that finishes before the view is built leaves the canvas permanently "loading"

**File:** `app/ui/canvas_view.py:235-246` (with `app/ui/canvas_page.py:47-76`)
**Issue:** `_resync_once` always calls `begin_loading()` (reads_in_flight 1 -> 2) but only balances it with `_end_read` when `not self._gone()`. `_gone()` is `self._root is None or self._root.is_deleted`, and `_root` is only set in `build()`. The view is registered with the hub at `canvas_page.py:49`, but built only after `await services.sessions.list_cards(...)` (line 53) and the banner. If the hub completes a recovery in that window (`_resync_listeners` -> `request_resync`), the resync task's read can return while `_root is None`; `_gone()` is then true, `_end_read` is skipped, and `_reads_in_flight` stays at 1 after the page's own `load_snapshot`. From then on `loading` is permanently true: every `apply_card`/`remove_card` is buffered forever, the tab silently stops receiving live updates, and no warning is shown. The window is narrow (a hub recovery must land during a page open), but the failure is silent and unrecoverable without a reload, and the unbuilt state is exactly the case `_gone()` conflates with "tab closed".
**Fix:** Separate "never built" from "deleted". Only skip the read accounting when the client is actually gone:
```python
def _gone(self) -> bool:
    return self._root is not None and self._root.is_deleted

# _resync_once: when _root is None the snapshot is still valid input for _end_read;
# _replace_state/_apply must then tolerate an unbuilt view (e.g. skip the snapshot
# when self._root is None and let the page-open load_snapshot supply it):
if self._root is None:
    self._end_read(None)          # balance begin_loading, keep buffering for the page read
elif not self._gone():
    self._end_read(cards)
```
Add a test that triggers `request_resync()` on a registered-but-unbuilt view and then asserts a later `apply_card` is rendered.

### WR-02: `_cancel` swallows the caller's own cancellation

**File:** `app/realtime/hub.py:61-67` (used at 369-370 and 481-482)
**Issue:** `with contextlib.suppress(asyncio.CancelledError, Exception): await task` cannot tell "the awaited task was cancelled" from "the task running `_cancel` was itself cancelled while waiting". The second case is swallowed. Concretely, `stop()` cancels `_recovery_task`; if that task is inside `_cancel(self._supervisor_task)` / `_cancel(self._resubscribe_task)` (lines 369-370) at that instant, its cancellation is eaten, the loop body continues, and `_recover` goes on to close the client, build a new one, `start()` and (on success) call `_resync_listeners()` and `_start_supervisor()` after `stop()` returned, leaking a connected client and a supervisor task. The same pattern also means a cancelled `stop()` (for example a shutdown timeout) swallows its own cancel. The window is tiny, so it is latent rather than frequent, but it is a classic asyncio defect in the shutdown path.
**Fix:** Only suppress the cancellation of the child, and re-raise if the current task is being cancelled:
```python
async def _cancel(task):
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling():   # we were cancelled, not just the child
            raise
    except Exception:
        pass
```
Additionally check `if self._stopping: return` after `await self.start(...)` / before `_start_supervisor()` in `_recover` as defense in depth.

### WR-03: `list_cards` silently truncates at PostgREST `max_rows` (1000) and the resync then deletes the rest from the screen

**File:** `app/db/repository.py:100-112` (consumed by `app/ui/canvas_view.py:204-214`)
**Issue:** `supabase/config.toml` sets `max_rows = 1000` (the hosted default is also 1000). The query has no explicit range or pagination, so a workspace with more than 1000 live cards returns only the first 1000 in order with no error. `_replace_state` treats the snapshot as authoritative and removes every shown card not in it, so a reconnect/resync would make cards beyond row 1000 vanish from every canvas even though they exist, and the page-open view would be incomplete. The agent snapshot in a later phase will inherit the same helper if reused. Unlikely for a four-quadrant boundary canvas, but the failure is silent and destructive to the view.
**Fix:** Page the read, or fail loudly when the cap is hit:
```python
rows: list[dict] = []
start = 0
while True:
    resp = await (query.range(start, start + 999).execute())
    rows += resp.data
    if len(resp.data) < 1000:
        return rows
    start += 1000
```
(or enforce a per-session card cap in `add_card`).

### WR-04: Hard-coded latency thresholds against the hosted network make the convergence test flaky

**File:** `tests/integration/test_live_cards.py:195-197`
**Issue:** `assert max(latencies) <= 2.0` and `median <= 1.0` over only five cards measure the developer's network, hosted Realtime load and CDC lag, not the code under test. A single slow Realtime delivery (the same path whose startup probe is given 15-20 s elsewhere) fails the suite and gets re-run until green, which erodes the integration suite's signal. The convergence assertions further down are the actual correctness check.
**Fix:** Keep the correctness assertions hard and downgrade the latency to a reported figure or a generous bound (for example `max <= 10.0`), or gate the strict thresholds behind an opt-in env var / marker.

## Info

### IN-01: `_end_read` is not exception-safe, so one failing apply loses the rest of the buffer

**File:** `app/ui/canvas_view.py:190-202`
**Issue:** `_reads_in_flight` is decremented and `self._pending` is swapped out before replay. If `_replace_state` or a replayed `_apply` raises, either the remaining buffered events are dropped (swap already done) or, if `_replace_state` raises, `_pending` is left populated while the view is no longer loading, so those stale entries replay on the next resync after a newer snapshot. Because `updated_at` is not bumped by edits (no touch trigger), the stale-row guard cannot protect against that replay.
**Fix:** Wrap each replayed event in `try/except Exception` with a one-line warning (class name only), and perform the pending swap in a `finally` so the state machine always returns to a consistent "live, empty buffer" state.

### IN-02: Cross-workspace UPDATE removal is effectively dead on the hosted project

**File:** `app/realtime/hub.py:189-198`, test `tests/unit/test_hub_dispatch.py:307-317`
**Issue:** The DELETE branch documents that hosted Postgres Changes sends only the primary key in `old_record` when RLS is on, even with replica identity full. The same applies to UPDATE `old_record`, so `old_record.get("workspace_id")` will normally be absent and the "remove from old workspace" path never fires in production; the unit test passes only because it feeds a full `old_record`. Cards cannot change workspace through the app (composite FK, no UI), so this is unreachable-by-design today.
**Fix:** Either apply the same "remove from all canvases when the old workspace is unknown" fallback to UPDATE, or document that cross-workspace moves are unsupported and drop the dead branch/test.

### IN-03: DB text CHECK and service trimming disagree for non-space whitespace and bound only the trimmed length

**File:** `supabase/migrations/20261022000000_init_schema.sql` (cards.text check), `app/services/sessions.py:56-67`
**Issue:** Postgres `btrim` strips spaces only; Python `str.strip()` strips all Unicode whitespace. Through the app both agree (the service strips first), but a direct writer can store `"\n\n"` as a "non-blank" card, and `char_length(btrim(text)) <= 500` puts no bound on the raw length (a 1 MB string of padding spaces around one character passes). The README advertises that outside writers' rows appear live, so such rows would render on every canvas.
**Fix:** Add `char_length(text) <= 500` (or a generous raw cap) in a follow-up migration, and decide whether the DB should use `btrim(text, E' \t\r\n')`.

### IN-04: `_after_resubscribe` relies on `assert` and leaves state stuck when no probe is configured

**File:** `app/realtime/hub.py:297`, `310`
**Issue:** `assert self._write_probe is not None` is stripped under `python -O`, and when `start()` was used without `run_startup_check` (only tests do this), `_on_channel_state` sets `state = "reconnecting"` and `_schedule_recovery` silently returns, so `/healthz` stays degraded forever. Production always sets the probe, so this is hygiene.
**Fix:** Replace the assert with an explicit guard that logs once and either leaves the state unchanged or raises a clear error.

### IN-05: Stale docstring in identity.py

**File:** `app/ui/identity.py:7-9`
**Issue:** The module docstring says "Phase 2's add-card handler must `await ensure_display_name(...)`", but that handler now exists (`canvas_view._add_card`). The forward-looking sentence is misleading.
**Fix:** Reword to describe the present contract ("the add-card handler awaits `ensure_display_name` and aborts on None").

### IN-06: Forward-referencing lambda for `on_name_saved` in the page function

**File:** `app/ui/canvas_page.py:47`, `64-70`
**Issue:** `CanvasView(view, on_name_saved=lambda name: on_name_saved(name))` references a function defined 20 lines later, and that function in turn reads `banner`/`header_name` assigned later. It works only because the callback is first invoked after all are bound; any reordering or an early invocation raises `UnboundLocalError`/`NameError`.
**Fix:** Define `header_name`, `banner` and `on_name_saved` before constructing `CanvasView` (or have `CanvasView` take a setter after construction) and pass the function directly.

### IN-07: Test doubles have drifted from the production contracts

**File:** `tests/ui/fakes.py:109`, `tests/integration/test_live_cards.py:72-85`, `tests/unit/test_hub_dispatch.py:189-204`
**Issue:** `FakeRepository.insert_card` checks `1 <= len(author) <= 40` without `btrim`, so it does not mirror the new `cards_author_nonblank` constraint that this phase added (a `"   "` author passes the fake; only the service guard stops it). Two `RecordingListener` classes omit `request_resync` although `CardListener` requires it; a hub recovery during those tests would log a failed resync warning instead of exercising the protocol.
**Fix:** Use `len(author.strip(" "))` in the fake and add a no-op `request_resync` to both recording listeners.

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
