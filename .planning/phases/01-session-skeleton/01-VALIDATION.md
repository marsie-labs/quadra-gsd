---
phase: "1"
slug: "session-skeleton"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: true
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

Mapped from PLAN.md files 01-01 … 01-06 (one row per task; full verify commands and `<fails_when>` live in each plan's `<verify>`).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01 | 1 | QUAL-04 | T-01-SC | Package legitimacy approved before any install | manual (checkpoint:human-verify) | — (blocking human gate) | n/a | ⬜ pending |
| 01-01-T2 | 01 | 1 | QUAL-04 | T-01-01..03 | `.env`/`.nicegui/` gitignored before scaffold; deps import | smoke + lint | `uv run python -c "import fastapi, nicegui, supabase, …; print('imports-ok')" && git check-ignore -q .env …`; `uv run ruff check .` | ❌ W0 | ⬜ pending |
| 01-01-T3 | 01 | 1 | QUAL-04 | T-01-01..03 | Settings require secrets (`SecretStr`) | unit | `uv run pytest tests/unit/test_settings.py -q` | ❌ W0 | ⬜ pending |
| 01-02-T1 | 02 | 2 | SESS-03, SESS-04, SESS-05, QUAL-04 | T-01-04..09 | Migration pushed (RLS, revoked grants, atomic RPC); open-link render + unknown-link 404 | integration (tracer) | `supabase migration list --linked --agent no \| grep -E '20261022000000 +\| +20261022000000'`; `uv run pytest -m integration tests/integration/test_skeleton_e2e.py -q -rs`; `uv run pytest -q` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 02 | 2 | SESS-01, SESS-02 | T-01-04..09 | Home form mints `secrets.token_urlsafe(16)`, lands on `/s/<id>` | integration | `uv run pytest -m integration "tests/integration/test_skeleton_e2e.py::test_create_from_home_lands_on_canvas" -q -rs`; `uv run pytest -q` | ❌ W0 | ⬜ pending |
| 01-03-T1 | 03 | 3 | SESS-01, SESS-02, SESS-05 | T-01-10..13 | Project-name validation; malformed id → 404 without DB; one-shot collision retry | unit + ui | `uv run pytest tests/unit/test_tokens.py tests/unit/test_sessions_service.py tests/ui/test_home.py tests/ui/test_not_found.py -q` | ❌ W0 | ⬜ pending |
| 01-03-T2 | 03 | 3 | SESS-02, SESS-03, SESS-04 | T-01-10..13 | Atomic create; DB-side CHECKs; publishable key denied | integration | `uv run pytest -m integration tests/integration/test_create_session.py tests/integration/test_rls_denies_anon.py -q -rs` | ❌ W0 | ⬜ pending |
| 01-04-T1 | 04 | 3 | QUAL-04 | T-01-14..16, T-01-24 | Nonce-matched startup probe (strict/warn/off); keys/WS URL never logged | unit + integration | `uv run pytest tests/unit/test_hub_dispatch.py -q`; `uv run pytest -m integration tests/integration/test_realtime_probe.py -q -rs -k roundtrip_via_hub` | ❌ W0 | ⬜ pending |
| 01-05-T1 | 05 | 4 | QUAL-04, IDEN-02 | T-01-14, T-01-17..19, T-01-24, T-01-25 | `/healthz` before `ui.run_with`; 1-year signed cookie; single worker; no `ui.timer` in app/ | unit + integration + grep | `uv run pytest tests/unit/test_app_factory.py tests/unit/test_hub_dispatch.py -q`; `awk … app/main.py`; `uv run pytest -m integration tests/integration/test_realtime_probe.py -q -rs` | ❌ W0 | ⬜ pending |
| 01-05-T2 | 05 | 4 | QUAL-04 | T-01-25 | README documents setup; no key values in README | doc grep | `grep -qF "## Configure" README.md && …`; `! grep -qE 'sb_secret_…\|eyJ…' README.md` | ❌ W0 | ⬜ pending |
| 01-06-T1 | 06 | 5 | IDEN-01, IDEN-02, SESS-04 | T-01-20..23 | Inline banner; name persists per browser, read-only; text via `ui.label` only; second browser opens without login | unit + ui | `uv run pytest tests/unit/test_identity.py tests/ui/test_identity.py tests/ui/test_canvas.py -q` | ❌ W0 | ⬜ pending |
| 01-06-T2 | 06 | 5 | IDEN-01 (D-02; groundwork for IDEN-03 → Phase 2) | T-01-20..23 | `ensure_display_name()` blocks then completes; no placeholder author; DB author CHECK parity | ui + unit + integration | `uv run pytest tests/ui/test_ensure_name.py tests/unit/test_identity.py tests/ui/test_identity.py -q`; `uv run pytest -m integration tests/integration/test_card_author_check.py -q -rs` | ❌ W0 | ⬜ pending |

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (01-01-T1 is a blocking human checkpoint)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test files are created by the TDD tasks that verify them)
- [x] No watch-mode flags
- [ ] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
