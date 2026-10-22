---
phase: "1"
slug: "session-skeleton"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-22"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1 + pytest-asyncio 1.4 (`asyncio_mode=auto`) + `nicegui.testing.user_plugin` |
| **Config file** | none — Wave 0 installs (`pyproject.toml` `[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -q` (excludes `integration` marker by default) |
| **Full suite command** | `uv run pytest -q -m "integration or not integration"` (requires `.env` with Supabase keys) |
| **Estimated runtime** | ~5 seconds quick; ~30 seconds full (hosted Supabase round-trips) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest -q -m "integration or not integration"` + `uv run ruff check . && uv run ruff format --check .`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; rows are seeded per requirement from RESEARCH.md and refined when PLAN.md files exist.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SESS-01 | — | Project name validated (trim, 1–100) before create | ui (fake service) | `uv run pytest tests/ui/test_home.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SESS-02 | session-id guessing | `secrets.token_urlsafe(16)`; DB CHECK rejects short/invalid token | unit + integration | `uv run pytest tests/unit/test_tokens.py -q`; `uv run pytest -m integration tests/integration/test_create_session.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SESS-03 | — | `create_session` RPC atomic (no partial rows on failure) | integration | `uv run pytest -m integration tests/integration/test_create_session.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SESS-04 | publishable-key access | Anon/authenticated denied by RLS + revoked grants; app works without login | ui + integration | `uv run pytest tests/ui/test_canvas.py -q`; `uv run pytest -m integration tests/integration/test_rls_denies_anon.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SESS-05 | session-id enumeration | Uniform 404 for unknown/malformed id; malformed id never hits DB | ui | `uv run pytest tests/ui/test_not_found.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IDEN-01 | stored XSS | Banner shown, canvas visible; user text rendered via `ui.label` only | ui | `uv run pytest tests/ui/test_identity.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IDEN-02 | cookie forgery | Name persists across reload/sessions via signed storage cookie; no rename UI | ui | `uv run pytest tests/ui/test_identity.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IDEN-03 | — | `validate_display_name` (trim/empty/≤40/duplicates ok); `ensure_display_name` blocks then completes | unit + ui | `uv run pytest tests/unit/test_identity.py tests/ui/test_ensure_name.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | QUAL-04 | secret leakage | Settings require secrets (`SecretStr`); `/healthz`; hub dispatch; probe round-trip; keys/WS URL never logged | unit + integration | `uv run pytest tests/unit -q`; `uv run pytest -m integration tests/integration/test_realtime_probe.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` (pytest config, markers, `asyncio_mode=auto`), `uv.lock`, `.python-version`
- [ ] `tests/conftest.py` — env fixtures; skip `integration` tests when `.env` missing
- [ ] `tests/ui/ui_main.py` harness + `FakeServices`
- [ ] `tests/unit/test_tokens.py`, `test_identity.py`, `test_settings.py`, `test_hub_dispatch.py`
- [ ] `tests/ui/test_home.py`, `test_canvas.py`, `test_not_found.py`, `test_identity.py`, `test_ensure_name.py`
- [ ] `tests/integration/test_create_session.py`, `test_realtime_probe.py`, `test_rls_denies_anon.py` (optional `SUPABASE_PUBLISHABLE_KEY`; skip if absent); cleanup via service-role DELETE of created `workspaces`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| README reproduces setup from clean clone | QUAL-04 | Needs user's Supabase keys and hosted project | Follow README: create `.env`, `supabase db push --linked`, start app; confirm startup Realtime check passes |
| Two real browsers see same session | SESS-04, IDEN-02 | Real browser cookies/separate profiles | Create session in browser A, open link in browser B (private window), set names, reload both |
| Which Realtime key works (`sb_secret_` vs legacy JWT) | QUAL-04 | Depends on hosted project behavior | Start app with strict check; on failure set `SUPABASE_REALTIME_KEY` to legacy `service_role` JWT; record outcome in README |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
