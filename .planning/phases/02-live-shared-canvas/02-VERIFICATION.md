---
phase: 02-live-shared-canvas
verified: 2026-10-23T12:30:00Z
status: human_needed
score: 5/6 must-haves verified
covered_files:
  - ".planning/phases/02-live-shared-canvas/02-01-PLAN.md"
  - ".planning/phases/02-live-shared-canvas/02-01-SUMMARY.md"
  - ".planning/phases/02-live-shared-canvas/02-02-PLAN.md"
  - ".planning/phases/02-live-shared-canvas/02-02-SUMMARY.md"
  - ".planning/phases/02-live-shared-canvas/02-03-PLAN.md"
  - ".planning/phases/02-live-shared-canvas/02-03-SUMMARY.md"
  - ".planning/phases/02-live-shared-canvas/02-04-PLAN.md"
  - ".planning/phases/02-live-shared-canvas/02-04-SUMMARY.md"
  - ".planning/phases/02-live-shared-canvas/02-05-PLAN.md"
  - ".planning/phases/02-live-shared-canvas/02-05-SUMMARY.md"
  - "README.md"
  - "app/db/repository.py"
  - "app/models.py"
  - "app/realtime/hub.py"
  - "app/services/sessions.py"
  - "app/ui/canvas_page.py"
  - "app/ui/canvas_view.py"
  - "app/ui/identity.py"
  - "supabase/migrations/20261023000000_author_nonblank.sql"
  - "tests/integration/test_live_cards.py"
  - "tests/integration/test_realtime_recovery.py"
  - "tests/integration/test_restart_recovery.py"
covered_digest: "v3:sha256:0ca91551bf3bf512dee73b5b68c2fa3fea8fb44b41d396a1ec28bda024039260"
behavior_unverified: 1
behavior_unverified_items:
  - truth: "When another tab of the same browser saved a different name while this tab's name dialog was open, the card's author is the name now in effect (the value save_display_name returns), never the dialog's raw input (backstop truth from 02-02)"
    test: "In one browser open the session in tab A and tab B, both unnamed. In tab A type card text and click Add so the name dialog opens (leave it open). In tab B save the name 'Zed' through the banner. In tab A enter 'Amy' in the dialog and Continue."
    expected: "The card is stored with author 'Zed' (the name already in effect), not 'Amy'."
    why_human: "The code path is correct on reading (ensure_display_name submits the value returned by save_display_name, which never overwrites an existing name), and test_save_never_overwrites_an_existing_name covers that function, but no test drives the dialog with a concurrently saved name. Non-inferable multi-tab storage behaviour, so presence plus wiring is not evidence."
advisory: []
gaps: []
human_verification:
  - test: "Two real browsers, live card (SC2). Run `uv run python -m app`, open one session link in two real browsers (one private window), name browser A, add a card in IS."
    expected: "Browser B shows the card within about a second, in IS, as 'author · HH:MM' with the full timestamp on hover."
    why_human: "Real WebSocket rendering, perceived latency and tooltip are visual; the NiceGUI user-fixture test (test_card_added_in_one_browser_appears_live_in_another) has no real browser."
  - test: "SQL-editor demo (SC3). With the session open in both browsers, run the insert from README 'Live updates' in the Supabase Dashboard SQL editor, then the text update, then `deleted_at = now()`."
    expected: "The row appears in IS in both browsers with no reload, the edit shows, then the card disappears."
    why_human: "The integration test uses a second supabase client as a stand-in for the SQL editor; the editor itself and real browsers are not exercised."
  - test: "Browser offline/online (SC4). In browser A, DevTools > Network > Offline for ~10 s; add a card in browser B; set A back online."
    expected: "A shows the card without a manual reload."
    why_human: "The reconnect handshake is simulated by invoking connect_handlers in tests; a real socket drop and NiceGUI's reconnect behaviour are not."
  - test: "Server restart (SC4). Ctrl-C the server, add a card via the SQL editor, start the server again, reload both browsers, then GET /healthz."
    expected: "Both browsers show every card including the one added while down; /healthz reports realtime 'verified'."
    why_human: "The restart integration test fetches the page over HTTP; real browser reload and Ctrl-C shutdown are not exercised."
  - test: "Name dialog, inline error, double-click (SC1). In a fresh private window type text in IS and Add; Cancel; Add again, enter a name, Continue. Then Add on an empty field and with a 501-character paste. Then double-click Add quickly."
    expected: "Cancel keeps the text and writes nothing; Continue stores 'name · HH:MM' and removes the banner; 'Card text is required (max 500 characters)' appears under that field only; one card appears on double-click."
    why_human: "Visual placement of the error, dialog behaviour and real double-click timing."
---

# Phase 2: Live Shared Canvas Verification Report

**Phase Goal:** Participants add cards to any quadrant, and every connected browser on the session sees them appear live, relayed by the Python server from Supabase Realtime.
**Verified:** 2026-10-23T12:30:00Z
**Status:** human_needed
**Re-verification:** No, initial verification

## Goal Achievement

The goal is achieved in the codebase as far as automated evidence can show. The add path, the Realtime relay through `RealtimeHub`, the DB-direct projection, reconnect/restart resync and recovery of the hub's own socket are all implemented, wired and exercised by passing tests, including 22 integration tests against hosted Supabase that I re-ran. Status is `human_needed` because the plans' own end-of-phase checks need real browsers, and one backstop truth has no behavioural test. Two code-review warnings (WR-01, WR-03) are real defects in the resync path and are recorded below as warnings, not gaps.

### Observable Truths (ROADMAP success criteria are the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Participant can add a text card to any quadrant; empty text and text over 500 characters are rejected with a message | VERIFIED | `canvas_view._build_quadrant` builds an input and Add button per quadrant; `_add_card` calls `validate_card_text` first and sets `field.error = CARD_TEXT_ERROR` ("Card text is required (max 500 characters)"); `SessionService.add_card` re-validates before any repository call (trim, 1..500 code points). Tests: `test_cards.py::test_blank_text_*`, `test_oversized_text_*`, `test_500_code_points_are_stored_and_shown`, `test_card_rules.py` (500/501, multibyte), `test_card_authoring.py` (name gate, double submit, failure). DB backs it with `char_length(btrim(text)) between 1 and 500`. |
| 2 | A card added in browser A appears in browser B within ~1s without refresh, with author and time; stored with quadrant, order index, author and timestamps | VERIFIED (latency by integration test, real browser needs human) | `add_card` -> `Repository.insert_card` (workspace_id, quadrant_id, text, author, order_index with 1024 gap; id/created_at/updated_at from DB defaults). Hub `_on_card` fans INSERT/UPDATE/DELETE to listeners of the row's workspace; `CanvasView.apply_card` upserts keyed by id and renders `author · HH:MM` with tooltip. `test_live_cards.py::test_card_added_in_one_browser_appears_live_in_another` (two NiceGUI clients, hosted Supabase, DB row asserted) and `test_two_clients_converge_with_latency` (5 cards, max <= 2.0 s, median <= 1.0 s) pass. `test_card_storage.py` proves CARD-07 columns. |
| 3 | A card row inserted directly in the database appears live in open browsers (proves Realtime, not polling) | VERIFIED (SQL editor itself needs human) | `test_outside_writer_changes_appear_live` uses a separate supabase client that bypasses Repository/SessionService: insert, text update, `deleted_at` update and hard DELETE each reach the open canvas. Static scan: no `ui.timer`, no polling loop in `app/`; the only `while` loops are the single-flight resync rerun loop, the recovery backoff loop and the probe resend loop, all reactive. DELETE with only the primary key (hosted RLS behaviour) is handled by fan-out to all canvases (`test_delete_with_only_the_primary_key_removes_from_every_canvas`). |
| 4 | After a browser reconnect or a server restart, the canvas shows every card, including ones added while disconnected | VERIFIED (automated paths; real reconnect needs human) | Page open is read-then-render with hub registration before the read and event buffering (`canvas_page.py`, `canvas_view._end_read`). Reconnect handshake after the first calls `request_resync()` (`on_connect`). Hub rebuilds a closed/errored socket, re-proves CDC with a nonce probe, then calls `request_resync()` on every canvas. Tests: `test_restart_recovery.py` (real app subprocess run twice, card written while down is in the page), `test_realtime_recovery.py` (forced socket close, card written during outage found by resync, later card live again, no key in logs), `test_canvas_recovery.py` (reconnect handshake, buffering vs older snapshot, coalescing, failure keeps cards, 503 not 404), `test_hub_recovery.py`. See warnings WR-01 and WR-03 for two edges. |
| 5 | An automated integration test against Supabase shows two clients converging on the same cards via Realtime | VERIFIED | `test_two_clients_converge_with_latency`: two listeners on one workspace plus a foreign-session listener; after 5 adds both hold exactly the stored card ids in `card_sort_key` order, and the foreign listener receives nothing. Re-ran `uv run pytest -m integration -q`: 22 passed. |
| 6 | (02-02 backstop truth) A card's author is the name now in effect when another tab saved a different name during the dialog | PRESENT_BEHAVIOR_UNVERIFIED | `ensure_display_name` submits `save_display_name(field.value)`, which returns the existing name if one is stored (code read). No test drives the dialog with a concurrently saved name. Routed to human verification per the non-inferable-truth rule. |

**Score:** 5/6 truths verified (1 present, behavior-unverified)

### Plan must_haves cross-check (spot-verified in code, beyond the roadmap SCs)

| Plan truth | Status | Evidence |
|------------|--------|----------|
| Own card shown exactly once despite echo (keyed by id) | VERIFIED | `_apply` removes any existing widget for the id before rendering; `test_own_card_renders_once_even_after_echo` |
| Identical text/author renders as two cards | VERIFIED | keyed by id; `test_identical_cards_both_shown` |
| Stale event (older `updated_at`) ignored | VERIFIED | `_apply` guard `card.updated_at < shown.updated_at`; `test_stale_update_is_ignored` |
| Listener unregistered when client deleted | VERIFIED | `client.on_delete` -> `hub.unregister`; `test_listener_unregistered_when_client_deleted` |
| Malformed event dropped with class-only warning; one failing canvas does not block others | VERIFIED | `_on_card` try/except + `_fan_out` per-listener isolation; hub dispatch tests |
| Single-flight recovery, backoff 1,2,4,8,16,30,30..., sanitized logs, bounded probe write, `reconnecting` is degraded on /healthz | VERIFIED | `_schedule_recovery`, `RECOVERY_BACKOFF`, `_sanitize`, `verify_roundtrip` `wait_for` on write; `test_hub_recovery.py` |
| Author-nonblank migration applied to hosted DB | VERIFIED | `test_card_author_check.py` (live, passes: space-only author rejected 23514) |
| README Phase 2 docs (live cards, SQL demo, reconnect, `reconnecting`, REALTIME_CHECK=off, second migration) | VERIFIED | README sections "Live cards", "Live updates", "Reconnects and restarts", migrations table row for 20261023000000, REALTIME_CHECK=off warning |

### Deferred Items

None. The edit/delete/move UI is Phase 3 and is not a Phase 2 gap.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/ui/canvas_view.py` | CanvasView with add, keyed apply, snapshot/resync protocol | VERIFIED | 264 lines, substantive, used by `canvas_page.py`, data flows from `list_cards` and hub events |
| `app/ui/canvas_page.py` | read-then-render page, 503 path, reconnect resync | VERIFIED | wired to hub and services |
| `app/realtime/hub.py` | cards binding, registry, fan-out, recovery, supervisor | VERIFIED | `table="cards"` binding added before the single subscribe; constructed in `main.py` lifespan |
| `app/services/sessions.py` | `add_card`, `list_cards`, validators | VERIFIED | validation precedes repository calls |
| `app/db/repository.py` | `insert_card`, `max_order_index`, `list_cards` | VERIFIED | only PostgREST path; see WR-03 for missing pagination |
| `app/models.py` | `CardView`, `card_sort_key`, `SessionView.workspace_id` | VERIFIED | |
| `supabase/migrations/20261023000000_author_nonblank.sql` | btrim CHECK constraints | VERIFIED | enforced on hosted DB (live test) |
| Tests (unit, ui, integration) | per plan | VERIFIED | `uv run pytest -q`: 179 passed, 22 deselected; `-m integration`: 22 passed; `ruff check .` clean |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `canvas_view._add_card` | `SessionService.add_card` | `get_services().sessions.add_card(...)` after `ensure_display_name` | WIRED |
| `canvas_page` | `RealtimeHub` | `hub.register(canvas_view)` before the card read; `on_delete` unregister | WIRED |
| `RealtimeHub._build_channel` | `cards` publication | `on_postgres_changes(All, self._on_card, table="cards")` | WIRED |
| `SessionService` | `Repository` | `max_order_index` + `insert_card`, `list_cards` | WIRED |
| `main.py` lifespan | `deps.services` | `Services(sessions=SessionService(repo), hub=hub)` | WIRED |
| `canvas_page.on_connect` | `CanvasView.request_resync` | every handshake after the first | WIRED |
| `RealtimeHub._recover` / `_after_resubscribe` | `listener.request_resync()` | `_resync_listeners()` after nonce re-proof | WIRED |
| `main.py` `/healthz` | `hub.status()` | state not in (verified, disabled) -> degraded | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| `CanvasView` cards | `_cards` | `list_cards` PostgREST select + Realtime `record` | yes | FLOWING |
| Card widgets | `card.text`, `author`, `created_at` | `CardView` from DB row | yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Offline suite | `uv run pytest -q` | 179 passed, 22 deselected | PASS |
| Live suite vs hosted Supabase | `uv run pytest -m integration -q` | 22 passed | PASS |
| Lint | `uv run ruff check .` | All checks passed | PASS |

Logging was left at default; no DEBUG capture of the `realtime` logger.

### Probe Execution

Step 7c: SKIPPED. No `probe-*.sh` scripts exist or are declared; the hub's runtime nonce probe is covered by the integration tests above.

### Requirements Coverage

All nine IDs from the ROADMAP phase line appear in PLAN frontmatter (02-01: CARD-01, CARD-06, IDEN-03, SYNC-01, SYNC-02, QUAL-02; 02-02: CARD-01, CARD-06, CARD-07, IDEN-03; 02-03: SYNC-01, SYNC-02, SYNC-03, QUAL-02, CARD-06; 02-04: SYNC-04, SYNC-02; 02-05: SYNC-04, SYNC-01, SYNC-02, QUAL-02). REQUIREMENTS.md maps exactly these nine to Phase 2. No orphaned requirements.

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| IDEN-03 | 02-01, 02-02 | Display name recorded as author | SATISFIED | add path passes stored name as author; name gate with no placeholder; `InvalidCardAuthor`; DB `cards_author_nonblank`; live test asserts `author == "Ann"` |
| CARD-01 | 02-01, 02-02 | Add text card to any quadrant, empty rejected, max 500 | SATISFIED | see Truth 1 |
| CARD-06 | 02-01, 02-02, 02-03 | Card shows author name and time | SATISFIED | `author · HH:MM` label + tooltip (`test_cards.py`, live test sees "Ann") |
| CARD-07 | 02-02 | Card stores quadrant, order index, author, created/updated, deleted timestamp | SATISFIED | schema + `test_card_storage.py` (live) |
| SYNC-01 | 02-01, 02-03, 02-05 | Change appears for others within ~1s | SATISFIED (human confirm in real browsers) | convergence test thresholds max 2.0 s / median 1.0 s; see WR-04 on flakiness |
| SYNC-02 | 02-01, 02-03, 02-04, 02-05 | Delivered via Realtime relayed by Python, no polling | SATISFIED | hub relay; no timers/polling in `app/` |
| SYNC-03 | 02-03 | DB-direct changes appear live | SATISFIED (SQL editor demo is a human check) | `test_outside_writer_changes_appear_live` |
| SYNC-04 | 02-04, 02-05 | After reconnect/restart client shows current state | SATISFIED with caveats | restart + recovery integration tests; WR-01 and WR-03 edges below |
| QUAL-02 | 02-01, 02-03, 02-05 | Integration tests vs real Supabase verify propagation between two clients | SATISFIED | three live files plus convergence test |

### Anti-Patterns Found

Debt-marker scan (`TBD|FIXME|XXX|TODO|HACK`) over `app/`, `supabase/`, `README.md`, `tests/`: none. No stubs, no hardcoded-empty render data.

Open code-review findings (02-REVIEW.md; 0 critical, 4 warnings, all recorded "open" in 02-REVIEW-DISPOSITION.md). I checked WR-01 against the code and it is real:

| File | Finding | Severity | Impact on this phase's goal |
|------|---------|----------|------------------------------|
| `app/ui/canvas_view.py:235-246` with `canvas_page.py:47-76` (WR-01) | `_resync_once` skips `_end_read` when `_root is None` (view registered but not yet built), leaving `_reads_in_flight` at 1 forever after the page's own `load_snapshot`; the canvas then buffers every event and silently stops updating. | WARNING | Needs a hub recovery to land during the page-open card read. Narrow race, silent and unrecoverable without reload. Touches SYNC-04 and SYNC-01 on that tab only. No test covers it. |
| `app/db/repository.py:100-112` (WR-03) | `list_cards` has no pagination; PostgREST `max_rows` is 1000, so beyond 1000 live cards the snapshot truncates and `_replace_state` removes the rest from the screen. | WARNING | Unlikely for a four-quadrant boundary canvas; silent and destructive if hit. Also inherited by the Phase 5 agent snapshot if it reuses the helper. |
| `app/realtime/hub.py:61-67` (WR-02) | `_cancel` can swallow the caller's own cancellation during shutdown. | WARNING | Latent shutdown-path defect; no effect on goal behaviour. |
| `tests/integration/test_live_cards.py:195-197` (WR-04) | Hard latency thresholds (2.0 s max, 1.0 s median over 5 samples) measure the network; may flake. | WARNING | Test-signal quality only; it passed on this run. |
| IN-01 to IN-07 | Exception safety of `_end_read`, dead cross-workspace UPDATE branch on hosted RLS, DB/service whitespace rule drift (no raw-length cap), `assert` in hub, stale docstring, forward-referencing lambda, test-double drift | INFO | None blocks the goal. |

Disposition: I recommend fixing WR-01 and WR-03 before Phase 4/5 builds on this resync and snapshot path, or recording an explicit `deferred`/`skipped` decision. They do not turn any success criterion to FAILED, because every tested and ordinary path of SC4 holds.

### Process deviations weighed

- No UI-SPEC.md for Phase 02 (ui.safety-gate waived by the human): visual quality is therefore unaudited, which is why layout and error placement sit in the human checks.
- The 02-01 tracer feedback gate did not pause: a process gap, with no code consequence visible; the tracer's live test passes.
- The 02-02 schema push was run by the human: verified independently, since the live `test_card_author_check.py` passes against the hosted DB.

### Human Verification Required

See `human_verification` and `behavior_unverified_items` in the frontmatter (5 end-of-phase checks plus 1 backstop truth).

### Gaps Summary

No blocking gaps. The phase goal is evidenced by passing offline and live tests and by direct reading of the wiring. Remaining work before calling Phase 2 fully done: the real-browser end-of-phase checks, the multi-tab author backstop check, and a triage decision on code-review warnings WR-01 and WR-03.

---

_Verified: 2026-10-23T12:30:00Z_
_Verifier: Claude (gsd-verifier)_
