---
phase: 02-live-shared-canvas
plan: 01
subsystem: realtime-ui
tags: [nicegui, supabase-realtime, postgres-changes, fastapi, pydantic, pytest]

requires:
  - phase: 01-session-skeleton
    provides: hosted schema (cards table, publication, replica identity full), RealtimeHub startup check, canvas page, ensure_display_name gate
provides:
  - CardView / card_sort_key domain types and SessionView.workspace_id
  - Repository.insert_card / max_order_index / list_cards (only PostgREST card path)
  - SessionService.add_card / list_cards with gapped order_index (ORDER_GAP 1024)
  - RealtimeHub cards Postgres Changes binding with register / unregister / listener_count registry and _on_card fan-out keyed by workspace_id
  - CanvasView (quadrant columns, per-quadrant add field, keyed apply_card) wired into the canvas page
  - Live two-browser integration proof and offline UI proofs
affects: [02-02-authoring-rules, 02-03-live-fidelity, 02-04-reconnect-recovery, 02-05-realtime-recovery]

actuals:
  tokens: 8260
  tasks: 2
  commits: 3

plan_head_before: 4e92ff46a283cf4bbf94493f3ca771fa12789e71
plan_head_after: 7f8b62b702e78d45a9c97c4409b24153154e1858
commits: 3

tech-stack:
  added: []
  patterns:
    - "Keyed upsert of card widgets (by card id) so the actor's confirmed write and the Realtime echo render one card"
    - "Hub registry keyed by workspace_id; plain-def _on_card callback that never raises and isolates each listener in try/except"
    - "Register with the hub before reading the snapshot; client.on_delete unregisters the view"

key-files:
  created:
    - app/ui/canvas_view.py
    - tests/integration/test_live_cards.py
    - tests/ui/test_cards.py
  modified:
    - app/models.py
    - app/db/repository.py
    - app/services/sessions.py
    - app/deps.py
    - app/main.py
    - app/realtime/hub.py
    - app/ui/canvas_page.py
    - tests/conftest.py
    - tests/ui/fakes.py

key-decisions:
  - "Card times render in the server process's local zone as HH:MM with the full timestamp and zone name as tooltip (A-02)"
  - "No timestamp normalizer needed: Realtime created_at parses with plain pydantic datetime (A-01)"
  - "Two-browser tests open the unnamed browser first and the acting browser last, because the NiceGUI test plugin runs click handlers under the most recently opened request's storage"

requirements-completed: [CARD-01, CARD-06, IDEN-03, SYNC-01, SYNC-02, QUAL-02]

coverage:
  - id: D1
    description: "A named participant adds a card in a quadrant; it is stored in hosted Supabase with the stored display name as author"
    requirement: "CARD-01"
    verification:
      - kind: integration
        ref: "tests/integration/test_live_cards.py#test_card_added_in_one_browser_appears_live_in_another"
        status: pass
    human_judgment: false
  - id: D2
    description: "A second browser on the same session shows the new card in the same quadrant without a reload, delivered by RealtimeHub from the Supabase Realtime cards event"
    requirement: "SYNC-02"
    verification:
      - kind: integration
        ref: "tests/integration/test_live_cards.py#test_card_added_in_one_browser_appears_live_in_another"
        status: pass
      - kind: unit
        ref: "tests/ui/test_cards.py#test_other_browser_sees_card_only_after_realtime_event"
        status: pass
    human_judgment: false
  - id: D3
    description: "Each card shows its text and an '<author> · HH:MM' meta line with the full timestamp as tooltip"
    requirement: "CARD-06"
    verification:
      - kind: unit
        ref: "tests/ui/test_cards.py#test_other_browser_sees_card_only_after_realtime_event"
        status: pass
    human_judgment: true
    rationale: "The tooltip content and visual presentation of the meta line are not asserted by any test; only the meta text is"
  - id: D4
    description: "Opening or reloading a canvas shows every stored live card in its own quadrant in (order_index, created_at, id) order; soft-deleted rows stay hidden; empty quadrants show 'No cards yet'"
    requirement: "SYNC-01"
    verification:
      - kind: unit
        ref: "tests/ui/test_cards.py#test_reopened_canvas_shows_stored_cards_in_order"
        status: pass
      - kind: unit
        ref: "tests/ui/test_cards.py#test_soft_deleted_rows_are_not_shown_on_open"
        status: pass
    human_judgment: false
  - id: D5
    description: "The acting browser shows its own card exactly once; another session's event never renders; a deleted client leaves the hub registry"
    requirement: "QUAL-02"
    verification:
      - kind: unit
        ref: "tests/ui/test_cards.py#test_own_card_renders_once_even_after_echo"
        status: pass
      - kind: unit
        ref: "tests/ui/test_cards.py#test_event_for_another_session_is_not_rendered"
        status: pass
      - kind: unit
        ref: "tests/ui/test_cards.py#test_listener_unregistered_when_client_deleted"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-23
status: complete
---

# Phase 2 Plan 1: Live Card Tracer Summary

**A card added in one NiceGUI browser is stored in hosted Supabase and appears in a second browser through the Python RealtimeHub's `cards` Postgres Changes binding (keyed by workspace_id), with a snapshot read on page open and a keyed-upsert CanvasView so the actor sees its own card once.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-23T10:33:10Z
- **Completed:** 2026-10-23T10:39:26Z
- **Tasks:** 2
- **Files modified:** 12 (3 created, 9 modified)

## Accomplishments

- Tracer path proven live against hosted Supabase: browser A add field -> `SessionService.add_card` -> `Repository.insert_card` -> `cards` -> Postgres Changes -> `RealtimeHub._on_card` -> registry by workspace_id -> `CanvasView.apply_card` -> browser B. Add click to browser B showing the card was **616 ms** in the live test (observed value, quantized by the test user's 100 ms retry polling; it includes the order-index read, the insert and Realtime delivery).
- Hub owns a listener registry (`register`, `unregister` idempotent, `listener_count`) and a plain-def `_on_card` that never raises, never logs payloads and isolates each listener.
- Reopened canvases read every live card (`deleted_at is null`) in `(order_index, created_at, id)` order; the hub is registered first so an in-between insert still arrives and the keyed upsert keeps it single.
- Full suite: 102 passed (96 baseline + 6 new), 14 hosted integration tests passed (`-m integration`), ruff check and format clean, regression greps clean.

## A-01 Raw Realtime timestamp

Raw `created_at` delivered in a live `cards` Realtime record: `'2026-10-23T10:37:07.93594+00:00'` (`updated_at` identical). It parses with plain pydantic `datetime`, so **no timestamp normalizer was needed**. Note the fractional part is not zero-padded to 6 digits (`.93594`), which pydantic accepts. The PostgREST read format is `'2026-10-23T10:37:33.619077+00:00'`.

## TDD record (Task 2)

- **RED (`207ed11`):** Before the snapshot read existed, exactly the two snapshot tests failed, on the planned assertion that the quadrant card column was empty:
  - `test_reopened_canvas_shows_stored_cards_in_order` (`assert [] == ['earlier', 'later']`)
  - `test_soft_deleted_rows_are_not_shown_on_open` (the visible seeded card was not on the page)
- **Green guards by design at RED (4):** `test_own_card_renders_once_even_after_echo`, `test_other_browser_sees_card_only_after_realtime_event`, `test_event_for_another_session_is_not_rendered`, `test_listener_unregistered_when_client_deleted`. They protect behavior already delivered by the tracer.
- **GREEN (`7f8b62b`):** `Repository.list_cards`, `SessionService.list_cards`, snapshot application in the canvas page. 6 passed.
- **REFACTOR:** none needed.
- Semantic RED assessment: the target tests executed and failed on the intended assertion (empty column because no snapshot read existed); no import, fixture or collection faults. The `gsd_run check tdd-red-evidence` classifier was not run: `gsd_run` is not installed in this environment and `workflow.tdd_mode` is not enabled; pytest text output is also not one of the classifier's supported report formats.

## Task Commits

1. **Task 1: Tracer, card added in browser A appears live in browser B** - `827c7be` (feat)
2. **Task 2 RED: failing tests for the card snapshot on canvas open** - `207ed11` (test)
3. **Task 2 GREEN: show every stored card when a canvas opens** - `7f8b62b` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified

- `app/ui/canvas_view.py` - `CanvasView`, `format_card_time`, `format_card_timestamp`; four quadrant columns, per-quadrant add field, keyed `apply_card`
- `app/realtime/hub.py` - `CardListener`, registry, `cards` binding (second, after `realtime_probe`), `_on_card` fan-out
- `app/models.py` - `CardView`, `card_sort_key`, `SessionView.workspace_id`
- `app/db/repository.py` - `CARD_COLUMNS`, `insert_card`, `max_order_index`, `list_cards`
- `app/services/sessions.py` - `ORDER_GAP`, `next_order_index`, `add_card`, `list_cards`, `workspace_id` population
- `app/deps.py`, `app/main.py` - `Services.hub`, hub built before the service container
- `app/ui/canvas_page.py` - builds `CanvasView`, registers with the hub, unregisters on client delete, applies the snapshot
- `tests/conftest.py` - `real_services` carries an unstarted hub; new strict-verified `live_services` fixture
- `tests/ui/fakes.py` - fake card repository methods mirroring DB constraints, `seed_card`, `card_event`
- `tests/integration/test_live_cards.py` - live two-browser proof
- `tests/ui/test_cards.py` - six offline proofs

## Decisions Made

- Card time uses the server's local zone as `HH:MM` with a full timestamp plus zone name tooltip (A-02, as planned).
- No timestamp normalizer on `CardView` (A-01 confirmed by the live record).
- `Services` is built after the hub in the lifespan; `app.state.hub`, startup check mode behavior and shutdown order are unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two-browser tests must open the acting browser last**
- **Found during:** Task 1 (live test, first run: browser A's Add click never reached the service)
- **Issue:** NiceGUI's `User.click` runs the handler directly in the test task, so `app.storage.user` resolves through the most recently opened request. With the plan's order (A named, then `create_user()` B opened), A's `current_name()` read B's empty storage and `ensure_display_name` opened the name dialog instead of returning "Ann". This is a test-harness artifact, not an app defect (each browser has its own session in the real app).
- **Fix:** Open the unnamed second browser first and the acting named browser last, in the live test and in the offline two-browser tests. Semantics are unchanged: B is open and unnamed before A adds the card, and stays open.
- **Files modified:** tests/integration/test_live_cards.py, tests/ui/test_cards.py
- **Verification:** live test passes; offline two-browser tests pass.
- **Committed in:** 827c7be, 207ed11

**2. [Rule 1 - Bug] Live test assertion could pass on the typed input value**
- **Found during:** Task 1
- **Issue:** `user.should_see(text)` matches the add field's own value, so it passed before the card existed.
- **Fix:** Scope the assertion to `marker="cards-DOES"` with `retries=50`, so it proves the rendered card.
- **Files modified:** tests/integration/test_live_cards.py
- **Committed in:** 827c7be

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug in test assertion)
**Impact on plan:** Both are test-harness corrections; no production behavior or scope changed.

## Issues Encountered

- Running the live test with `--log-cli-level=DEBUG` made realtime-py print the Realtime access token (the hosted secret key) into the tool output. It was not written to any committed file; the scratch output file was deleted at once. Never use DEBUG log capture for the `realtime` logger against the hosted project; the hub's own INFO pin only applies once `app.realtime.hub` is imported before logging is configured. Consider rotating that key if the session transcript is retained anywhere shared.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Threat Flags

None - no network endpoints, auth paths or schema changes beyond the plan's threat model (T-02-01 to T-02-06 mitigations implemented and verified: workspace-keyed fan-out, label-only rendering, stored display name as author, per-listener isolation with `on_delete` unregistration, no payload logging, no package installs).

## Next Phase Readiness

- Plans 02-02 to 02-05 can build on the stable contracts (`CardView`, `Repository` card methods, `SessionService.add_card/list_cards`, hub `register/unregister/listener_count/_on_card`, `CanvasView.apply_card`, UI markers, `card_event`/`seed_card` test helpers).
- Known follow-ups already assigned: text validation and error messages (02-02), UPDATE/DELETE projection (02-03), buffered snapshot and 503 page (02-04), Realtime recovery (02-05).
- When writing multi-browser UI tests, open the acting browser last (see deviation 1).

## Self-Check: PASSED

All created files exist on disk (`app/ui/canvas_view.py`, `tests/integration/test_live_cards.py`, `tests/ui/test_cards.py`); commits `827c7be`, `207ed11`, `7f8b62b` are ancestors of HEAD; `test(02-01)` and `feat(02-01)` commits present in order.

---
*Phase: 02-live-shared-canvas*
*Completed: 2026-10-23*
