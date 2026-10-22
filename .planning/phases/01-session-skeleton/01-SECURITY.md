---
phase: "1"
slug: "session-skeleton"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-22"
---

# Phase 1 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (01-01 … 01-06 `<threat_model>` blocks); mitigations verified by gsd-security-auditor (ASVS L1, block_on: high).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| PyPI → developer machine | Third-party packages installed into the project venv | package code (supply chain) |
| Developer shell/.env → repo | Secrets live in a local file that must never be committed | Supabase secret key, storage secret (high) |
| Settings object → logs/console | A config object holding keys could be printed | secrets (high) |
| Browser → home form / URL path | Untrusted project names and arbitrary `/s/` path segments enter the Python process | user text, path tokens |
| Browser → canvas page | Untrusted display-name input rendered to every participant later | user text (stored XSS surface) |
| Browser cookie → server-side user storage | Signed session cookie selects which stored name a browser gets | session id cookie |
| Python server → Supabase PostgREST | Server holds the secret key; DB must still enforce shape and access | rows, RPC calls |
| Public internet → Supabase PostgREST | Anyone with the publishable key can hit the Data API directly | anon requests |
| Python server ↔ Supabase Realtime (WSS) | Key travels in the WebSocket URL query; events flow back into the process | key (high), change events |
| Python process → console/logs | uvicorn, lifespan and hub write to the developer's terminal | diagnostics that could echo keys/URLs |
| Anyone on localhost → /healthz | Unauthenticated status endpoint | realtime status only |
| Repo → readers | README.md is committed and could carry a pasted key | documentation |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-SC | Tampering | dependency installs (uv add) | high | mitigate | Blocking-human legitimacy gate; `uv tree --depth 1` = approved 10; `uv.lock` committed 6c109bc, unchanged since; `uv lock --check` passes | closed |
| T-01-01 | Information Disclosure | .env with SUPABASE_SECRET_KEY | high | mitigate | `.gitignore:6` `.env` in first scaffold commit; `git check-ignore -q .env` = 0; only `.env.example` ever tracked; history scan finds only unit-test fake keys | closed |
| T-01-02 | Information Disclosure | app/settings.py repr/str | medium | mitigate | `SecretStr` (settings.py:20,22,24); `test_repr_and_str_never_reveal_secret_values` | closed |
| T-01-03 | Spoofing | NiceGUI cookie signed with STORAGE_SECRET | medium | mitigate | Required, no default, ≥32 chars (settings.py:24,30-38); tests at test_settings.py:56,63; main.py:78 → NiceGUI SessionMiddleware | closed |
| T-01-04 | Information Disclosure | session_id capability in /s/{session_id} | high | mitigate | `secrets.token_urlsafe(16)` (tokens.py:12); DB unique + regex CHECK; e2e asserts 22 chars / 16 bytes | closed |
| T-01-05 | Elevation of Privilege | tables + create_session RPC vs anon/authenticated | high | mitigate | Migration: RLS on all 4 tables, revoke all from anon/authenticated, EXECUTE only to service_role, `security invoker`, `search_path=''` | closed |
| T-01-06 | Tampering | project name on canvas (stored XSS) | medium | mitigate | `ui.label` only (canvas_page.py:22); no html/markdown/run_javascript/v-html under app/ | closed |
| T-01-07 | Information Disclosure | secret key reaching the browser | high | mitigate | No Settings/SecretStr in app/ui; keys only server-side (repository.py:13, main.py:54,78, hub.py); pages call `get_services().sessions` | closed |
| T-01-08 | Tampering | partial session rows on failed create | medium | mitigate | Single plpgsql `create_session` transaction; one `.rpc` call; `test_failed_create_leaves_no_rows` | closed |
| T-01-09 | Denial of Service | canvas page awaiting slow DB | low | accept | See Accepted Risks (AR-01); `response_timeout=10` | closed |
| T-01-10 | Tampering | project name input (empty/oversized) | medium | mitigate | `validate_project_name` in UI + service; DB CHECK 1-100; code-point parity tests (é×100/101, 23514) | closed |
| T-01-11 | Information Disclosure | /s/ probing with malformed ids | medium | mitigate | `SESSION_ID_RE.fullmatch` before any DB call; single 404 body; test_not_found (get_calls==0) | closed |
| T-01-12 | Elevation of Privilege | publishable key vs tables/RPC | high | mitigate | `test_publishable_key_cannot_call_create_session` / `..._read_workspaces` assert 42501 — ran live, not skipped | closed |
| T-01-13 | Denial of Service | unauthenticated session creation (spam) | low | accept | See Accepted Risks (AR-02) | closed |
| T-01-14 | Information Disclosure | Realtime `?apikey=` / keys in hub logs | high | mitigate | Logger guard (hub.py:28-32); `_sanitize` on every stored/logged error; `from None`; never logs `_rt.url`; hub tests (see Follow-ups R1, R2) | closed |
| T-01-15 | Spoofing | startup check false success | medium | mitigate | Only this run's nonce resolves the waiter; SUBSCRIBED alone never verifies; hub unit tests | closed |
| T-01-16 | Denial of Service | startup hanging on Realtime | medium | mitigate | connect retries ×5, subscribe 15 s, probe 15 s; strict raises `RealtimeCheckError`, lifespan aborts (see Follow-up R5) | closed |
| T-01-17 | Information Disclosure | /healthz payload | low | mitigate | Fixed `{status, realtime{state, stage, latency_ms, error}}`, sanitized error; shape pinned in test_app_factory | closed |
| T-01-18 | Information Disclosure | session ids in uvicorn access logs | low | accept | See Accepted Risks (AR-03) | closed |
| T-01-19 | Spoofing | 1-year NiceGUI session cookie | low | accept | See Accepted Risks (AR-04) | closed |
| T-01-20 | Tampering | display name in header (stored XSS) | medium | mitigate | `ui.label`/`.text` only; 40-char cap; `test_header_name_is_read_only_text` | closed |
| T-01-21 | Spoofing | duplicate display names | low | accept | See Accepted Risks (AR-05) | closed |
| T-01-22 | Tampering | invalid/empty author reaching cards | medium | mitigate | `ensure_display_name` returns None on cancel, no placeholder; DB CHECK 1-40 proven live (see Follow-up R4) | closed |
| T-01-23 | Tampering | forging another browser's stored name | low | mitigate | Signed SessionMiddleware cookie keys server-side `.nicegui/` storage (git-ignored) | closed |
| T-01-24 | Information Disclosure | keys in running app console | high | mitigate | `test_app_starts_and_proves_realtime` captures real subprocess console; asserts no key / `apikey=` (see Follow-up R1) | closed |
| T-01-25 | Information Disclosure | README `## Realtime key` | medium | mitigate | README names which key, never its value; key-shape gate = 0 matches | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-09 | `response_timeout=10` bounds the wait; local single-user v1 | Plan threat model (01-02), confirmed by gsd-security-auditor | 2026-10-22 |
| AR-02 | T-01-13 | Local v1 for 2-10 person teams; DB length CHECKs bound row size; rate limiting out of scope (RESEARCH Security Domain); default bind 127.0.0.1 | Plan threat model (01-03), confirmed by gsd-security-auditor | 2026-10-22 |
| AR-03 | T-01-18 | Dev logs stay on the developer's machine; ids are capabilities but logs never leave the host in v1 | Plan threat model (01-05), confirmed by gsd-security-auditor | 2026-10-22 |
| AR-04 | T-01-19 | Cookie only keys a non-authoritative display name; signed with STORAGE_SECRET; httponly + samesite=lax (Starlette default). Set `https_only=True` if ever served over TLS | Plan threat model (01-05), confirmed by gsd-security-auditor | 2026-10-22 |
| AR-05 | T-01-21 | D-04 allows duplicate names by design; link-based no-auth model; name is a label, not an identity | Plan threat model (01-06), confirmed by gsd-security-auditor | 2026-10-22 |

*Accepted risks do not resurface in future audit runs.*

---

## Follow-ups (non-blocking, beyond L1)

Residual observations from the auditor. None changes a threat status at ASVS L1; each needs a fix-or-accept decision before L2 or a non-local deployment.

| ID | Affects | Observation | Suggested fix |
|----|---------|-------------|---------------|
| R1 | T-01-14, T-01-24 | realtime-py logs `str(e)` at ERROR on failed connects, bypassing `_sanitize`. With a host-less `SUPABASE_URL` (e.g. `https:///x`, which passes supabase-py's URL check), websockets' InvalidURI message echoes the full `?apikey=<key>` URI to the local console. Reproduced offline with a fake key. | `logging.Filter` on the `realtime` logger applying the same masking, and/or require a hostname in the `SUPABASE_URL` setting |
| R2 | T-01-14 | The INFO pin on `realtime`/`websockets` loggers (hub.py:31) is conditional on import-time level. Safe with the shipped launcher, but a later DEBUG root config re-enables realtime-py's DEBUG URL log (contains key). | Set level unconditionally or use the R1 filter |
| R3 | T-01-07 | Plan wording "only repository.py touches keys" is stale: main.py and hub.py also hold keys (all server-side; boundary holds). | Doc-only |
| R4 | T-01-22 | `cards.author` CHECK uses `char_length(author)` without `btrim`; DB alone accepts whitespace-only author (app trims). | Phase 2 (IDEN-03): add `btrim` to the CHECK in a new migration |
| R5 | T-01-16 | Probe writes have no per-call 15 s bound (PostgREST client timeout 120 s); startup still bounded overall. | Wrap probe write in `asyncio.wait_for` |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-22 | 26 | 26 | 0 | gsd-security-auditor (opus), via /gsd-execute-phase 1 verify:post |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-22
