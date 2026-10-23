---
phase: "02"
slug: "live-shared-canvas"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-23"
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser -> NiceGUI server | Untrusted card text and display names enter the add handler and name dialog; the server decides author, quadrant and session | Card text, display name (user content) |
| Browser socket -> NiceGUI server | Reconnect handshakes trigger database reads on behalf of a link holder | Session id (capability link) |
| Supabase Realtime -> Python server | Postgres Changes payloads from any writer (app, SQL editor, scripts) are parsed and fanned out | Card rows |
| Python server -> Supabase (PostgREST / Realtime WSS) | Server holds the secret and Realtime keys; DB CHECKs and composite FK still enforce shape and placement | Secret key, card rows |
| Python server -> browsers | Projected card state is pushed to every canvas of a session | Card rows scoped per session |
| Any writer -> Supabase cards/workspaces | Non-UI writers bypass Python validation; only DB constraints apply | Card rows |
| /healthz -> local operator | Recovery state and errors exposed without authentication | Sanitized status strings |
| Developer CLI / test suite -> hosted Supabase | Migration push and integration tests change the shared hosted project | Schema, test rows |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-SC | Tampering | dependency installs | high | mitigate | No package installs in Phase 02; pyproject.toml and uv.lock last changed in 01-01 | closed |
| T-02-01 | Information Disclosure | RealtimeHub fan-out | high | mitigate | Workspace-keyed listener routing; tests/ui/test_cards.py::test_event_for_another_session_is_not_rendered | closed |
| T-02-02 | Tampering | stored XSS via card text/author | medium | mitigate | Label-only rendering; no ui.html/ui.markdown under app/ui; test_card_text_and_author_render_literally | closed |
| T-02-03 | Spoofing | card author | low | mitigate | Author from signed app.storage.user via ensure_display_name (app/ui/identity.py:77) | closed |
| T-02-04 | Denial of Service | failing canvas stopping fan-out | medium | mitigate | Per-listener try/except (app/realtime/hub.py:207); on_delete unregister (app/ui/canvas_page.py:51); test_listener_unregistered_when_client_deleted | closed |
| T-02-05 | Information Disclosure | Supabase keys reaching the browser | high | mitigate | No settings/secret references under app/ui; hub logs exception class names only | closed |
| T-02-06 | Elevation of Privilege | card placed into another session's quadrant | low | mitigate | Server-rendered quadrant ids; composite FK (quadrant_id, workspace_id) | closed |
| T-02-07 | Denial of Service | oversized or blank card text | medium | mitigate | validate_card_text (app/services/sessions.py:56); DB CHECK char_length(btrim(text)) 1-500; test_db_text_boundaries | closed |
| T-02-08 | Tampering | blank author/closer written outside the app | medium | mitigate | Migration 20261023000000_author_nonblank.sql; InvalidCardAuthor; tests/integration/test_card_author_check.py | closed |
| T-02-09 | Tampering | duplicate cards from double submit | low | mitigate | Per-quadrant in-flight flag; test_double_submit_creates_one_card | closed |
| T-02-10 | Denial of Service | card spam by a link holder | low | accept | See Accepted Risks Log AR-02-01 | closed |
| T-02-11 | Tampering | schema drift repo vs hosted DB | medium | mitigate | Append-only migration; `supabase migration list` evidence in 02-02-SUMMARY.md | closed |
| T-02-12 | Repudiation | placeholder author | low | mitigate | ensure_display_name aborts on None; test_unnamed_add_cancel_writes_nothing; no "Anonymous" under app/ | closed |
| T-02-13 | Denial of Service | malformed Realtime payload | medium | mitigate | CardView parse guarded, class-name-only warning (app/realtime/hub.py:195); test_malformed_event_is_dropped_without_payload_in_logs | closed |
| T-02-14 | Tampering | stale event overwriting newer state | low | mitigate | updated_at comparison (app/ui/canvas_view.py:145); test_stale_update_is_ignored | closed |
| T-02-15 | Information Disclosure | card moved across sessions leaving a copy | medium | mitigate | remove_card on old workspace listeners; test_update_across_workspaces_removes_from_old_session | closed |
| T-02-16 | Repudiation | integration suite passing vacuously | low | mitigate | integration_settings skips only for missing variables (tests/conftest.py:28) | closed |
| T-02-17 | Tampering | test rows left in hosted project | low | mitigate | finally-block cleanup in integration tests; cards cascade with workspace | closed |
| T-02-18 | Tampering | canvas state after missed events | medium | mitigate | Snapshot on open/reconnect with buffered replay; test_event_during_resync_beats_older_snapshot | closed |
| T-02-19 | Denial of Service | resync storm | low | mitigate | Single-flight resync; test_resync_requests_coalesce | closed |
| T-02-20 | Information Disclosure | DB error details on page/logs | low | mitigate | Fixed-text 503 page (app/ui/canvas_page.py:25); class-name-only logging | closed |
| T-02-21 | Denial of Service | valid link reported unknown during DB blip | low | mitigate | 503 not 404 on read failure; test_session_read_failure_returns_503 | closed |
| T-02-22 | Information Disclosure | keys in restarted app console | high | mitigate | test_server_restart_shows_cards_added_while_down asserts keys and apikey= absent | closed |
| T-02-23 | Information Disclosure | recovery warnings, hub.error, /healthz | high | mitigate | _sanitize (app/realtime/hub.py:134); test_recovery_logs_and_errors_are_sanitized | closed |
| T-02-24 | Denial of Service | reconnect hammering hosted project | low | mitigate | Single-flight capped backoff; test_recovery_backoff_sequence, test_channel_error_starts_one_recovery | closed |
| T-02-25 | Repudiation | silently dead subscription | medium | mitigate | Supervisor; /healthz reports reconnecting/degraded (app/main.py:42, app/realtime/hub.py:272) | closed |
| T-02-26 | Denial of Service | background tasks outliving shutdown | low | mitigate | stop() cancels and awaits tasks (app/realtime/hub.py:479) | closed |
| T-02-27 | Denial of Service | hung probe write | low | mitigate | asyncio.wait_for on probe writes (app/realtime/hub.py:419); test_probe_write_is_bounded | closed |
| T-02-28 | Tampering | realtime-py renaming private listen task | low | mitigate | test_listen_task_attribute_exists; uv.lock pin | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-10 | Link-based access with no accounts is a project constraint (PROJECT.md); 2-10 person teams; each card bounded to 500 code points | Plan 02-02 threat model | 2026-10-23 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-23 | 29 | 29 | 0 | /gsd-secure-phase (L1 grep-depth, plan-time register) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-23
