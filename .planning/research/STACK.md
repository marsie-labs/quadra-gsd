# Stack Research

**Domain:** Realtime collaborative workshop canvas (Python server-driven UI + Supabase Postgres + agent-facing REST API)
**Researched:** 2026-10-22
**Confidence:** HIGH for versions and core choices; MEDIUM for supabase-py Realtime with new-format secret keys (verify in Phase 1)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 (≥3.11) | Runtime | pydantic-settings 2.16 requires ≥3.11; NiceGUI 3.x requires ≥3.10; 3.12 is mature, fast asyncio |
| FastAPI | 0.159.x | HTTP app: agent REST endpoint, health, host for NiceGUI | User-specified; NiceGUI is built on FastAPI/Starlette and mounts into an existing app via `ui.run_with(app)` |
| NiceGUI | 3.18.x | Server-driven Python UI over WebSocket (socket.io) | User-specified. State lives server-side, so "Python relays to browser" is native: update UI elements in a client's context and NiceGUI pushes diffs |
| supabase (supabase-py) | 2.33.x | Postgres access via PostgREST + Realtime client | User-specified. **Realtime only works with the async client** (`acreate_client` / `AsyncClient`) |
| realtime (bundled with supabase) | 2.33.x | Realtime WebSocket client: `channel().on_postgres_changes(...)` | Pulled in by `supabase==2.33.0` (pinned equal version); supports server-side filters (`workspace_id=eq.<id>`) and `replication_ready` system event |
| Supabase PostgreSQL (hosted) | Project's version (15+/17) | Persistence, constraints, triggers, `supabase_realtime` publication | Existing hosted project; enforce immutability of closed sessions in DB, not just UI |
| uvicorn | 0.54.x | ASGI server | Standard for FastAPI/NiceGUI. **Run a single worker** (NiceGUI keeps per-client state in-process) |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.14.x | Domain models + REST response schemas | Card/Session models shared by DB layer, UI and agent endpoint |
| pydantic-settings | 2.16.x | Typed config from env / `.env` | `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `STORAGE_SECRET`, `APP_BASE_URL` |
| httpx | 0.28.x | Async HTTP client (supabase dep) + FastAPI test client transport | Agent endpoint tests via `httpx.AsyncClient(transport=ASGITransport(app))` |
| pytest | 9.1.x | Test runner | All tests |
| pytest-asyncio | 1.4.x | Async tests | Required by NiceGUI `user` fixture; set `asyncio_mode = auto` |
| nicegui testing plugin | (ships with nicegui) | Headless simulated-browser tests (`user` fixture) | UI behaviour tests without Selenium: `-p nicegui.testing.user_plugin` |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Env + dependency management, lockfile | `uv init`, `uv add ...`, `uv run pytest` |
| Supabase CLI | SQL migrations in `supabase/migrations/`, `supabase db push` to hosted project | Keep schema in version control; also enables optional `supabase start` local stack for integration tests |
| ruff | Lint + format | Single tool; replaces black/isort/flake8 |
| mypy or pyright (optional) | Type checking | Pydantic models + typed DB layer make this cheap |

## Installation

```bash
uv init --python 3.12
# Core
uv add "fastapi>=0.159" "nicegui>=3.18" "supabase>=2.33" "uvicorn[standard]>=0.54" "pydantic>=2.14" "pydantic-settings>=2.16"
# Dev
uv add --dev "pytest>=9.1" "pytest-asyncio>=1.4" httpx ruff
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| NiceGUI (server-driven) | React/Svelte SPA + supabase-js Realtime direct | If drag-and-drop, offline, or 50+ concurrent users per session matter; rejected because user wants Python end-to-end and Python as single gateway |
| `postgres_changes` (CDC) | Broadcast from Database (`realtime.broadcast_changes()` trigger, private channels) | Supabase recommends Broadcast for scale/security; at 2–10 users and one server-side subscriber, Postgres Changes is simpler and sufficient. Revisit if subscriber count or RLS complexity grows |
| supabase-py PostgREST for writes | asyncpg/psycopg direct SQL connection | If multi-statement transactions are needed outside RPC functions. Prefer Postgres functions called via `.rpc()` for atomic ops (create session + 4 quadrants, close session) |
| One global server subscription + in-process fan-out | One Realtime channel per open session | Per-session channels give server-side filtering but more channel lifecycle to manage; global is simpler at this scale |
| Hosted Supabase dev project for integration tests | Local `supabase start` (Docker) | Local stack gives isolated, resettable DB for CI; consider if tests start colliding with dev data |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Sync `create_client` for Realtime | Realtime in Python only works with the async client | `await acreate_client(url, key)` |
| Multiple uvicorn workers / gunicorn multi-process | NiceGUI client state and the in-process fan-out hub live in one process; clients on other workers would miss updates | Single worker; scale later with sticky sessions + Redis if ever needed |
| Polling loops (`ui.timer` re-querying DB) | Explicitly excluded by requirements; wasteful | Realtime `on_postgres_changes` → hub → NiceGUI clients |
| Exposing Supabase keys to the browser | Python is the single gateway; secret key bypasses RLS | Keep keys server-side only; enable RLS with no anon policies |
| NiceGUI global-scope "script mode" UI | Removed shared auto-index in 3.0; UI re-created per visit, can't mix with page functions | `@ui.page('/s/{session_id}')` page functions |
| Integer `order_index` renumbering on every move | Concurrent reorders cause write storms and conflicts | Fractional/gapped ordering (e.g., `double precision` midpoint, or gaps of 1024) |
| Legacy `service_role` JWT as long-term key | Legacy anon/service_role keys deprecated by end of 2026 | New `sb_secret_...` key (verify Realtime acceptance in Phase 1) |

## Stack Patterns by Variant

**If Realtime rejects the new `sb_secret_` key format in supabase-py:**
- Use the legacy `service_role` JWT for the Realtime connection only, behind the same settings object
- Because the realtime client README states the API key must be a JWT containing `exp` and `role` claims

**If integration tests become flaky against the shared hosted project:**
- Switch tests to local `supabase start` + `supabase db reset`
- Because isolation and deterministic seeding beat shared dev data

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| supabase 2.33.0 | realtime 2.33.0, postgrest 2.33.0, httpx >=0.26,<0.29 | Sub-packages pinned to same version; don't pin realtime separately |
| nicegui 3.18.0 | fastapi >=0.109.1 (!=0.123.5), starlette >=1.3.1, python-socketio >=5.16.2 | FastAPI 0.159 satisfies; let nicegui resolve starlette |
| pydantic-settings 2.16.1 | Python >=3.11 | Sets the Python floor for the project |
| pytest-asyncio 1.4.0 | pytest 9.x | Use `asyncio_mode = "auto"` for NiceGUI user fixture |

## Sources

- PyPI JSON API (pypi.org/pypi/<pkg>/json), queried 2026-10-22 — current versions, Python requirements, dependency pins (HIGH)
- https://supabase.com/docs/reference/python/realtime-api — async-only Realtime, `acreate_client` (HIGH)
- realtime-py README (PyPI) — `AsyncRealtimeClient`, `on_postgres_changes(event, schema, table, filter, callback)`, filter operators, `replication_ready`, JWT key requirement (HIGH)
- https://supabase.com/docs/guides/realtime/postgres-changes — publication, replica identity, RLS/DELETE caveats, throughput (HIGH)
- https://supabase.com/docs/guides/realtime/subscribing-to-database-changes and https://supabase.com/blog/realtime-broadcast-from-database — Broadcast recommended for scale (HIGH)
- https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys.md — publishable/secret keys, legacy deprecation end of 2026 (HIGH)
- https://nicegui.io/documentation/run, /section_configuration_deployment, /section_testing — storage_secret, background_tasks, testing plugins (HIGH)
- https://newreleases.io/project/pypi/nicegui/release/3.0.0 — 3.0 removed shared auto-index client (MEDIUM)

---
*Stack research for: realtime collaborative boundary canvas*
*Researched: 2026-10-22*
