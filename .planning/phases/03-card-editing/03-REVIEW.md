---
phase: 03-card-editing
reviewed: 2026-10-23T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - README.md
  - app/db/repository.py
  - app/models.py
  - app/services/sessions.py
  - app/ui/canvas_view.py
  - supabase/migrations/20261023120000_card_edit_tracking.sql
  - tests/integration/test_card_actions_live.py
  - tests/integration/test_card_edit_storage.py
  - tests/integration/test_card_reorder_live.py
  - tests/integration/test_live_card_edits.py
  - tests/ui/fakes.py
  - tests/ui/test_card_actions.py
  - tests/ui/test_card_editing.py
  - tests/ui/test_card_reorder.py
  - tests/ui/test_edit_concurrency.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-10-23
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

The phase adds inline edit, soft delete, move-to-quadrant and up/down reorder on top of the Phase 2 live canvas, backed by a `cards_touch` trigger. The service/repository layer is tight: every write is scoped by id, workspace and `deleted_at is null`, user text only reaches the page through `ui.label` text, a textarea value or `props[...]` item assignment (no XSS path), and the PostgREST filters are parameterised. The migration is correct (`search_path = ''`, qualified `clock_timestamp`, monotonic `updated_at`, `text_updated_at` unforgeable on UPDATE). `reorder_index` handles ties, edges and float exhaustion correctly in every case traced.

No security or data-corruption blockers were found. The defects are in failure handling and ordering robustness: a failed save throws away the participant's draft, a late Realtime echo can resurrect a card the participant just deleted, a reorder pair can become permanently un-swappable once float precision is exhausted, and `reorder_card` writes an order computed for one quadrant without checking the card is still in it. The tests are thorough but lean on fixed sleeps and copy-pasted helpers.

No `<structural_findings>` or external reviewer evidence was supplied.

## Warnings

### WR-01: A failed save discards the participant's draft

**File:** `app/ui/canvas_view.py:546-554` (also `app/ui/canvas_view.py:390-400`)
**Issue:** `_commit_edit` closes the editor (`_close_editor`, line 546) before the write starts. If `edit_card` then fails (network/PostgREST error) or raises `CardGone`, `_write` rolls the card back to the old text and shows "Could not save the card. Please try again." The text the participant typed (up to 500 code points) exists nowhere any more: the textarea is deleted, the optimistic row is popped, and the user must retype it. The README promises only "the card goes back and a message says so", but the test is named `test_failed_edit_rolls_back_with_a_message_and_stays_editable` and the retry in it types brand-new text, so the data-loss path is never exercised. Closing before the await is needed for the double-submit guard, but the draft should survive a failure. This is a likely scenario: Supabase hiccups or a Realtime/PostgREST blip are exactly when a person is mid-edit.
**Fix:** Keep the draft and reopen the editor on failure, e.g. pass an `on_failure` callback to `_write` (or have `_commit_edit` catch the outcome):
```python
async def _commit_edit(self, card_id):
    ...
    draft = clean
    self._close_editor(card_id)
    ok = await self._write(card_id, optimistic, call, EDIT_FAILED, "edit_card")  # make _write return bool
    if not ok and card_id in self._widgets and card_id not in self._editing:
        self._start_edit(card_id, draft=draft)  # reopen with the participant's text, not the server text
```
(`_start_edit` needs an optional `draft` argument; `_EditSession.original` must stay the server text.) Add a test that the editor value after a failed save equals the typed text.

### WR-02: A late Realtime echo can resurrect a card the participant just deleted

**File:** `app/ui/canvas_view.py:200-211` (with `:220-229`, `:401-404`)
**Issue:** `_apply` only runs the stale guard when the card is still in `self._cards`. `_remove` pops the card from `_cards`, so afterwards there is no `updated_at` baseline. Sequence: participant edits/moves/reorders a card, then deletes it; the delete's REST response arrives and `_write` calls `_remove` (or the optimistic delete is confirmed); then the Realtime echo of the *earlier* change (a live row with `deleted_at = null` and an older `updated_at`) is delivered. `shown is None`, so the guard is skipped, the card is stored and `_render` rebuilds it. It reappears (with a working menu) until the delete's own UPDATE event arrives, and permanently if that event is missed before a resync. The same applies to a "deleted elsewhere" removal on the `row is None` path (line 403) and to `CardGone`. REST responses and the Realtime socket are independent channels, so this ordering is realistic, particularly for the "edit then immediately delete" gesture.
**Fix:** Keep a tombstone with the deleting row's `updated_at` and let `_apply` compare against it:
```python
self._tombstones: dict[str, datetime] = {}   # card_id -> updated_at of the removal
# in _apply, before upserting a live row:
dead = self._tombstones.get(card.id)
if dead is not None and card.updated_at <= dead:
    return
# set in _write on a confirmed delete / CardGone / row-None, and in _apply when deleted_at is set
```
Clear tombstones in `_replace_state` for ids that reappear live with a newer `updated_at`. Add a UI test that feeds a stale live echo after a confirmed delete.

### WR-03: Move up/down becomes a silent no-op once float precision is exhausted

**File:** `app/services/sessions.py:61-62` (callers `app/services/sessions.py:231-233`, `app/ui/canvas_view.py:479-481`)
**Issue:** When no double lies strictly between the two bounds, `reorder_index` returns `None`; `reorder_card` then returns the card unchanged and `_reorder_card` returns without any feedback. Because every reorder swaps by halving the gap between two fixed neighbours (`(low + high) / 2`), repeatedly swapping the same two cards (a common "which goes first" tug-of-war) exhausts the gap in about 50 operations. After that the pair can never be swapped again: the Move up/down items remain enabled (`_refresh_quadrant` only looks at index, not at precision), the click does nothing and no message appears. Given the product (a team arguing over card order) this is reachable. The docstring and README ("never renumbered") present this as a design choice, but there is no recovery path at all.
**Fix:** When `reorder_index` returns `None` for a card that is not at an edge, fall back to a single-quadrant rebalance (an RPC that renumbers the quadrant's live cards by `ORDER_GAP` in one transaction) and then retry; at minimum surface a message ("Could not reorder this card") instead of silently doing nothing. Distinguish the edge case (return `None`, disabled item) from the exhausted case (return a sentinel/raise).

### WR-04: `reorder_card` writes an order computed for one quadrant without checking the card is still in it

**File:** `app/services/sessions.py:224-239`, `app/db/repository.py:164-168`
**Issue:** `reorder_card` does three independent round trips: `get_card`, `list_quadrant_order(row["quadrant_id"])`, then `set_card_order`. `set_card_order` only filters by id, workspace and `deleted_at is null`. If another participant moves the card to a different quadrant between the read and the write, the `order_index` calculated for the old quadrant's neighbours is applied in the new quadrant, landing the card at an arbitrary position there. The result is not corrupting (ties/positions are deterministic) but it is a move the user did not ask for, produced by a read-modify-write without a precondition. The same pattern causes duplicate `order_index` values for concurrent reorders: `test_concurrent_reorders_converge` in fact produces two cards at exactly `2560.0` and passes only because of the `created_at, id` tie-break.
**Fix:** Make the write conditional on the card's quadrant (and optionally its previous `order_index`) so a stale decision matches no row, then retry or return the fresh row:
```python
async def set_card_order(self, *, workspace_id, card_id, quadrant_id, order_index):
    return await self._update_live_card(
        workspace_id, card_id, {"order_index": order_index}, extra_eq={"quadrant_id": quadrant_id}
    )
```
(`_update_live_card` needs an optional extra filter parameter.) Treat `None` from this call as "retry once", not as `CardGone`, since the card may still exist.

### WR-05: `_write` can notify and render into a client that has already gone

**File:** `app/ui/canvas_view.py:390-410`
**Issue:** `_resync_once` carefully checks `self._gone()` after its await, but `_write` does not. A participant who closes the tab while a save/delete/move is in flight resumes in `_write` after the `await call()` and then calls `self._notify(CARD_GONE)`, `ui.notify(failure, ...)`, `_render`, and `widgets.card.delete()` on elements of a deleted client. Depending on the NiceGUI version this raises (for example from `with self._root:` on a deleted element or from `outbox` access) inside a background handler, and the exception propagates out of the `except` branches instead of being handled. At best it logs noise; at worst the `finally` still runs but the failure notification path is exercised against torn-down state.
**Fix:** Guard the post-await tail the same way resync does:
```python
row = await call()
if self._gone():
    return
```
and apply the same check in the `except` branches before notifying/rendering.

## Info

### IN-01: Unused fields on `_CardWidgets`

**File:** `app/ui/canvas_view.py:80-88`
**Issue:** `row` (the meta row) and `menu` are stored but never read anywhere in `app/` (grep confirms only the dataclass definition and construction).
**Fix:** Drop `row` and `menu` from the dataclass and from `_build_card`'s return, or add a comment if they are intentional hooks for Phase 4.

### IN-02: `deleted_at` is stamped with the app server's clock, everything else by the database

**File:** `app/db/repository.py:118-120`
**Issue:** `soft_delete_card` sends `datetime.now(UTC)` from the Python process while `created_at`/`updated_at` come from Postgres (`now()` / `clock_timestamp()`). With clock skew, `deleted_at` can be earlier than the card's `updated_at`, which later consumers (the agent snapshot) may find confusing. `_notify(self, message, type=...)` (line 631) also shadows the builtin `type`.
**Fix:** Let the database stamp it (an RPC, or a trigger that sets `deleted_at := clock_timestamp()` when it goes from null to non-null); rename the `type` parameter to `kind`.

### IN-03: Test helpers copy-pasted across five UI test files and three integration files

**File:** `tests/ui/test_card_actions.py:34-79`, `tests/ui/test_card_editing.py:42-100`, `tests/ui/test_card_reorder.py:158-216`, `tests/ui/test_edit_concurrency.py:32-106`, `tests/integration/test_card_actions_live.py:23-45`, `tests/integration/test_card_reorder_live.py:40-63`, `tests/integration/test_live_card_edits.py`
**Issue:** `_card_texts`, `_wait_for` (with differing retry counts and sleep intervals), `_card_element`, `_meta`, `_TypedNotify` and the integration `_new_session` are re-implemented in each file. They already diverge (0.02 s vs 0.1 s intervals, `next(iter(...))` vs tuple unpack), so a fix to one will not reach the others. `test_live_card_edits.py` also marks tests with `@pytest.mark.integration` per function while its siblings use `pytestmark`.
**Fix:** Move the shared helpers into `tests/ui/fakes.py` (or `tests/ui/helpers.py` / `tests/integration/helpers.py`) and import them; use `pytestmark` consistently.

### IN-04: Fixed `asyncio.sleep(0.1)` settles make several UI assertions timing-dependent

**File:** `tests/ui/test_card_reorder.py:280,306`, `tests/ui/test_card_actions.py:158,213,432,449,483`, `tests/ui/test_card_editing.py:309,435`
**Issue:** After a wait for the repository to change, tests sleep 0.1 s "to let the confirmed row reach the page" and then assert the UI state. The optimistic row and the confirmed row render identically, so the assertions pass whether or not the confirmation was processed, which means they do not actually verify the post-confirmation behaviour, and a slow runner can still race the sleep. The negative assertions after `sleep(0.1)` ("nothing was written") are weak in the same way.
**Fix:** Wait on an observable condition (for example `not view._busy`, or the menu button re-enabled as `test_double_enter_in_flight_writes_once_and_guards_the_card` already does) instead of a fixed delay.

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
