# Quadra

Quadra is a realtime collaborative boundary canvas. A small team opens a shared session via a link and fills four quadrants (IS, IS NOT, DOES, DOES NOT) with cards. When the session is closed, an external agent pulls the structured result by `session_id`.

It is Python end to end: FastAPI and NiceGUI for the server and UI, Supabase PostgreSQL for persistence, and Supabase Realtime events relayed by the Python server.

This README covers Phase 1 (session skeleton): create a session, open its unguessable link, enter a display name and see the four labeled quadrants, with the schema and the Realtime connection proven at startup.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) 0.7 or newer. It installs Python 3.12 itself.
- [Supabase CLI](https://supabase.com/docs/guides/cli) 2.121 or newer, logged in and linked to the hosted project:

```bash
supabase login
supabase link --project-ref fligjsqzjoyedcuolwss
```

## Configure

```bash
cp .env.example .env
```

`.env` is git-ignored. Keys stay server-side: Python is the only gateway to Supabase and no key is ever sent to a browser.

| Variable | Status | What it is and where to find it |
|----------|--------|---------------------------------|
| `SUPABASE_URL` | required | Hosted project URL, `https://<project-ref>.supabase.co` (Dashboard > Project Settings > API). |
| `SUPABASE_SECRET_KEY` | required | The `sb_secret_...` key (Dashboard > Project Settings > API Keys). Bypasses RLS, so server only. |
| `SUPABASE_REALTIME_KEY` | optional | Legacy `service_role` JWT, used only for the Realtime connection. Leave unset unless the startup check fails at stage `connect` with HTTP 401/403 (see [Realtime key](#realtime-key)). |
| `STORAGE_SECRET` | required | Signs the NiceGUI session cookie, at least 32 characters. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Changing it re-prompts every browser for its display name. |
| `APP_BASE_URL` | optional | Public base URL used to build shareable session links. Default `http://localhost:8080`. |
| `APP_HOST` | optional | Bind address. Default `127.0.0.1`. |
| `APP_PORT` | optional | Bind port. Default `8080`. |
| `REALTIME_CHECK` | optional | `strict` (default), `warn` or `off`. See [Startup Realtime check](#startup-realtime-check). |
| `SUPABASE_PUBLISHABLE_KEY` | tests only | The `sb_publishable_...` key. Used only by the integration test that proves anonymous access is denied. |

## Apply database migrations

The schema lives in `supabase/migrations/` and is pushed to the hosted project with the CLI:

```bash
supabase db push --linked --dry-run   # lists the migrations that would be applied
supabase db push --linked             # applies them
supabase migration list --linked      # Local and Remote columns should match
```

If the CLI asks for the database password, export `SUPABASE_DB_PASSWORD` in your shell for that command only. It never belongs in `.env`.

Fallback when the CLI cannot reach the project: paste `supabase/migrations/20261022000000_init_schema.sql` into the Dashboard SQL editor and run it, then record it as applied so the CLI stays in sync:

```bash
supabase migration repair --status applied 20261022000000 --linked
```

## Run

```bash
uv run python -m app
```

Then open `APP_BASE_URL` (default http://localhost:8080).

The app runs as a **single worker** on purpose. NiceGUI keeps per-client state in the server process and the Realtime hub fans events out in-process, so clients served by a second process would miss updates. The launcher hard-codes `workers=1`. Never use `--workers`, gunicorn or multiple processes.

## Startup Realtime check

Before the app serves requests, its lifespan proves that a database change event reaches the Python server through Supabase Realtime. It upserts a row in `realtime_probe` carrying a fresh random nonce and waits for the Postgres Changes event that carries that same nonce. A subscribed channel alone never counts as success.

On success the console shows (the number varies per run):

```
Realtime startup check verified: DB change event received in 348 ms
```

`REALTIME_CHECK` controls what a failure does:

| Value | On failure | `/healthz` realtime state |
|-------|------------|---------------------------|
| `strict` (default) | Startup stops with a message naming the failed stage and the likely fix. | the app does not start |
| `warn` | One ERROR is logged and the app starts anyway. | `failed` |
| `off` | The check is skipped and nothing connects at startup. | `disabled` |

The four failure stages:

| Stage | Meaning | Fix |
|-------|---------|-----|
| `connect` | The Realtime WebSocket was rejected, for example HTTP 401. | Set `SUPABASE_REALTIME_KEY` to the legacy `service_role` JWT (Dashboard > Project Settings > API Keys > Legacy API keys). |
| `subscribe` | The channel never reached SUBSCRIBED. | Check the key and that Realtime is enabled for the project. |
| `probe-write` | Writing the probe row failed. | Push the migrations (`supabase migration list --linked`) and check `SUPABASE_SECRET_KEY`. |
| `no-event` | The row was written but no matching change event arrived. | Push the migrations so `realtime_probe` is in the `supabase_realtime` publication. |

A strict failure takes about 15 seconds to surface when the key is rejected, because the Realtime client backs off before giving up.

`GET /healthz` returns JSON and exposes nothing else (no settings, URLs or keys):

```json
{"status": "ok", "realtime": {"state": "verified", "stage": null, "latency_ms": 348.05, "error": null}}
```

`realtime.state` is one of `pending` (no check has run), `verified`, `failed` or `disabled`. `status` is `ok` when the state is `verified` or `disabled`, otherwise `degraded`.

## Realtime key

Outcome of the live run on this project (2026-10-22): hosted Supabase Realtime **accepts the `sb_secret_` key** (`SUPABASE_SECRET_KEY`). `SUPABASE_REALTIME_KEY` was not set and the legacy JWT was not needed. The probe event round trip took roughly 0.35 to 1.3 seconds across runs.

So `SUPABASE_REALTIME_KEY` is an optional override. Set it only if the startup check fails at stage `connect` with HTTP 401/403, for example on a project whose Realtime still requires a legacy JWT. A deliberately wrong key was also tried: it fails loudly at stage `connect` with HTTP 401, and the key text does not appear in the error or the console.

## Tests

```bash
uv run pytest -q                       # unit and UI tests, no network
uv run pytest -m integration -q -rs    # hosted Supabase; needs .env
uv run ruff check . && uv run ruff format --check .
```

The integration suite needs `.env` with `SUPABASE_URL`, `SUPABASE_SECRET_KEY` and `STORAGE_SECRET`, plus `SUPABASE_PUBLISHABLE_KEY` for the anonymous-denial test (without it that test is reported as skipped). It includes a test that starts the real server as a subprocess, waits for `/healthz` to report `verified`, checks the one-year session cookie and asserts that no key appears in the console output.

## Project layout

```
app/
  __main__.py          single-worker launcher (uvicorn.run, workers=1)
  main.py              create_app(): lifespan, /healthz, NiceGUI mounted last
  settings.py          typed environment configuration
  deps.py              service container set by the lifespan
  models.py            view models shared by services and UI
  tokens.py            unguessable session link tokens
  db/repository.py     the only module that talks PostgREST
  services/sessions.py session creation and lookup, name and id validation
  realtime/hub.py      Realtime hub and startup round-trip check
  ui/                  NiceGUI pages: home, canvas, page registration
supabase/
  config.toml
  migrations/          SQL schema, pushed with the Supabase CLI
tests/
  unit/                settings, tokens, sessions service, hub, launcher and /healthz
  ui/                  NiceGUI user-fixture tests
  integration/         hosted-Supabase tests
```
