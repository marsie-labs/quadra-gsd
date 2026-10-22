# Phase 1: Session Skeleton - Pattern Map

**Mapped:** 2026-10-22
**Files analyzed:** 27 (new; nothing modified)
**Analogs found:** 0 in-repo / 27. The repo is greenfield. `git ls-files` outside `.planning/` returns only `.claude/CLAUDE.md`, and `supabase/` holds only untracked CLI state. `.claude/` GSD tooling is not a code analog.

All "analogs" below are the verified prototype snippets in `01-RESEARCH.md` (RESEARCH). Line numbers refer to that file. Phase 1 establishes the patterns that Phases 2-5 copy, so the planner should treat these excerpts as the canonical source.

## File Classification

| New File | Role | Data Flow | Reference (RESEARCH) | Match |
|---|---|---|---|---|
| `pyproject.toml` | config | n/a | Installation (99-104), Test harness (533-540) | research-snippet |
| `.python-version`, `uv.lock` | config | n/a | `uv python pin 3.12` (101) | research-snippet |
| `.gitignore` | config | n/a | Structure notes (199) | research-snippet |
| `.env.example` | config | n/a | Dotenv (553-561) | research-snippet |
| `README.md` | docs | n/a | QUAL-04 row (45), Open Q1, A5 | none |
| `supabase/config.toml` | config | n/a | from `supabase init` (major_version 17) | tool-generated |
| `supabase/migrations/20261022000000_init_schema.sql` | migration | CRUD / atomic RPC | Migration (303-406) | research-snippet (executed on PG17) |
| `app/__init__.py` | package | n/a | none | none |
| `app/__main__.py` | launcher | n/a | App factory + launcher (505-510) | research-snippet |
| `app/main.py` | app factory | request-response | Pattern 1 (201-204), factory (493-503) | research-snippet |
| `app/settings.py` | config | n/a | Dotenv note (562) | research-snippet |
| `app/deps.py` | service container | n/a | Pattern 2 (206-208) | research-snippet |
| `app/models.py` | model | transform | `QUADRANT_LABELS` (529), repository select (428-433) | research-snippet |
| `app/tokens.py` | utility | transform | Token (411-415) | research-snippet |
| `app/db/client.py` | service | request-response | `acreate_client` (CLAUDE.md) | none |
| `app/db/repository.py` | repository | CRUD / RPC | Repository (426-438) | research-snippet |
| `app/services/sessions.py` | service | request-response | Architectural map (59-61) | none |
| `app/realtime/hub.py` | service | event-driven | Hub (444-490) | research-snippet |
| `app/health.py` (or router in `main.py`) | route | request-response | `/healthz` spec (490) | spec only |
| `app/ui/pages.py` (`register_pages`) | route registry | n/a | Test harness (543-545), factory (499) | research-snippet |
| `app/ui/home_page.py` | component | request-response | Architecture diagram (146-149) | spec only |
| `app/ui/canvas_page.py` | component | request-response | Canvas skeleton (514-528), Pattern 3 (210-217) | research-snippet |
| `app/ui/identity.py` | utility / component | request-response | Token and name (417-422), Pattern 5, `ensure_display_name` (529) | research-snippet |
| `tests/unit/*` | test | transform | Token test spec (279), hub fake events (442) | spec only |
| `tests/ui/ui_main.py` and `tests/ui/test_*.py` | test | request-response | Test harness (531-550) | research-snippet |
| `tests/integration/*` | test | CRUD | Markers (539) | spec only |
| `tests/conftest.py` | test | n/a | pytest config (533-540) | none |

## Pattern Assignments

### `pyproject.toml` (config)
**Reference:** RESEARCH 99-104, 533-540.
Create it with `uv init --bare --python 3.12 --name quadra`, then `uv add` the deps listed at 102-103.
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
main_file = "tests/ui/ui_main.py"
addopts = "-p nicegui.testing.user_plugin -m 'not integration'"
markers = ["integration: needs real Supabase (SUPABASE_URL/SECRET_KEY) - run with -m integration"]
```
Add a `checkpoint:human-verify` immediately before the first `uv add` (Package Legitimacy Audit, line 127).

### `.gitignore`
Must contain `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.env`, `.nicegui/`, `supabase/.temp/` (line 199). Nothing exists today.

### `supabase/migrations/20261022000000_init_schema.sql` (migration)
**Reference:** RESEARCH 303-406. Copy the SQL verbatim. It was executed end-to-end on Postgres 17. It contains:
- the enums
- `workspaces`, `quadrants`, `cards` (the composite FK `(quadrant_id, workspace_id)`), and `realtime_probe`
- RLS enabled on all four tables, with `revoke ... from anon, authenticated` and explicit `grant ... to service_role` (Pitfall 2)
- `create_session` plpgsql with `set search_path = ''` and `revoke execute ... from public, anon, authenticated; grant execute ... to service_role` (Pitfall 3)
- `alter table public.cards replica identity full`
- the idempotent `foreach` publication block

Optionally append `notify pgrst, 'reload schema';` (A9). Mark `supabase db push --linked` as a `checkpoint:human-action`. The fallback is to paste the SQL into the dashboard SQL editor (A5). Confirm the `workspaces` vs `sessions` naming at plan review (A2).

### `app/tokens.py` (utility, transform)
```python
import re, secrets
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
def new_session_id() -> str:
    return secrets.token_urlsafe(16)
```
Do not use UUIDv4 (122 bits; Pitfall 6). The regex matches the DB CHECK.

### `app/ui/identity.py` (utility + dialog helper)
```python
MAX_NAME = 40
def validate_display_name(raw: str | None) -> str | None:
    name = (raw or "").strip()
    return name if 1 <= len(name) <= MAX_NAME else None
```
- Add `current_name()`, which reads `app.storage.user.get('display_name')`.
- Add `ensure_display_name()`, an awaitable `ui.dialog`. It returns the stored name if present. Otherwise it validates, shows the inline error "Name is required (max 40 characters)", writes `app.storage.user['display_name']`, and calls `dialog.submit(name)`. Cancel submits `None`.
- Phase 2 calls it before every authoring action (D-02). There is no "Anonymous" fallback.
- Use `ui.label`, never `ui.html` or `ui.markdown`, for user text.

### `app/db/repository.py` (repository, CRUD/RPC)
```python
from postgrest.exceptions import APIError
async def get_session(client, session_id: str):
    resp = await (client.table("workspaces")
                  .select("id, session_id, project_name, status, quadrants(id, kind, position)")
                  .eq("session_id", session_id).maybe_single().execute())
    return None if resp is None else resp.data   # Pitfall 7: None, not an empty response

async def create_session(client, project_name: str, session_id: str) -> str:
    resp = await client.rpc("create_session",
        {"p_project_name": project_name, "p_session_id": session_id}).execute()
    return resp.data
# On APIError code "23505": regenerate the token and retry once.
```
Also add `upsert_probe(nonce)`: `client.table("realtime_probe").upsert({"id": 1, "nonce": nonce}).execute()`. Sort quadrants by `position` in Python. The first integration test must confirm the embedded `quadrants(...)` select returns 4 rows.

### `app/db/client.py`
Use `await acreate_client(url, secret_key)` from the async supabase client only (CLAUDE.md "What NOT to Use"). There is no repo analog.

### `app/services/sessions.py` (service)
There is no snippet. Per the responsibility map (59-61):
- `create_session` trims and validates the project name (required, max 100 to match the DB CHECK), generates the token, and calls the repo.
- `get` returns `None` without a DB call if `SESSION_ID_RE` does not match.
- It never raises on an unknown id.

### `app/realtime/hub.py` (service, event-driven)
**Reference:** RESEARCH 444-490. Copy the `RealtimeHub` sketch: `start()` subscribes and `verify_roundtrip()` runs the probe loop. Rules:
- Callbacks must be plain `def` (Pattern 4).
- Add all bindings before the single `subscribe()` call.
- `on_postgres_changes(event, callback, table=..., schema=...)` takes the callback as the 2nd positional parameter.
- Treat `CHANNEL_ERROR` as a startup failure.
- Re-upsert the probe every ~3 s with a 15 s timeout (Pitfall 5).
- Never log the URL or the key; keep the `realtime` and `websockets` loggers at INFO or above (Pitfall 11).
- `REALTIME_CHECK` modes: strict (default) raises in the lifespan with a staged message (connect / subscribe / no-event-timeout) plus the `SUPABASE_REALTIME_KEY` legacy-JWT hint. `warn` logs and continues. `off` is for tests.
- Expose `state`, `error` and `latency_ms` for `/healthz`.

### `app/main.py` (app factory)
**Reference:** RESEARCH 493-503.
```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(lifespan=make_lifespan(settings), title="Quadra")
    app.include_router(health_router)     # every FastAPI route BEFORE run_with
    register_pages()
    ui.run_with(app, title="Quadra",
                storage_secret=settings.storage_secret.get_secret_value(),
                session_middleware_kwargs={"max_age": 365 * 24 * 3600})   # LAST
    return app
```
The lifespan order is: `acreate_client`, then repo, then service, then hub.start and the probe, then yield, then hub.stop and client close. It assigns `deps.services`. Add a test of the real factory's `/healthz` through `httpx.ASGITransport` (Pitfall 1).

### `app/__main__.py`
```python
uvicorn.run(create_app, factory=True, host="127.0.0.1", port=8080, workers=1)
```
`workers=1` is hard-coded.

### `app/settings.py`
Use `BaseSettings` with `SecretStr` fields and `SettingsConfigDict(env_file=".env", extra="ignore")`. The fields are:
- `supabase_url`
- `supabase_secret_key`
- `supabase_realtime_key` (optional)
- `storage_secret` (no default)
- `app_base_url`
- `realtime_check` (default `strict`)

### `app/deps.py`
A module-level `services: Services | None = None`. The lifespan sets it; the UI test harness sets fakes (Pattern 2). The `user` fixture does not run the outer lifespan.

### `app/ui/canvas_page.py`
**Reference:** RESEARCH 514-528.
- Use `@ui.page("/s/{session_id}", response_timeout=10)` (Pitfall 9).
- When the session is `None`, set `ui.context.client.status_code = 404`, then render the message and `ui.link("Create a new session", "/")`.
- The header shows the project name and the read-only display name.
- The banner appears only when `current_name()` is None (D-01) and is non-blocking.
- The 2x2 grid is `ui.grid().classes("grid-cols-1 md:grid-cols-2 gap-4 w-full")`, with one `ui.card().mark(f"quadrant-{kind}")` per quadrant, each with a label from `QUADRANT_LABELS` and "No cards yet".
- `QUADRANT_LABELS = {"IS": "IS", "IS_NOT": "IS NOT", "DOES": "DOES", "DOES_NOT": "DOES NOT"}` goes in `models.py`.

### `app/ui/home_page.py`
There is no snippet; it is spec only (diagram lines 146-149).
- `@ui.page('/')` with a project name input.
- Trim the input and require it (max 100) with an inline error.
- The button calls `deps.services.sessions.create_session`, then `ui.navigate.to(f'/s/{id}')`.

### Tests
- `tests/ui/ui_main.py`:
  ```python
  deps.services = FakeServices()
  register_pages()
  ui.run(storage_secret="test")
  ```
- Assert 404 with `await user.http_client.get(path)`, because `user.open()` asserts status 200 (Pattern 3).
- Use the `create_user` fixture for the second-browser test (SESS-04).
- Never `logger.error` on expected-failure paths, because the `user` fixture fails on ERROR logs (Pitfall 10).
- Unit tests cover:
  - tokens: 1000 unique, regex match, decodes to 16 bytes
  - name validation boundaries (0, 1, 40, 41, whitespace)
  - settings
  - hub dispatch with a fake `postgres_changes` message through `channel._handle_message` (line 442)
- Integration tests are marked `@pytest.mark.integration` and run against real Supabase:
  - the RPC creates 4 quadrants
  - `anon` is denied
  - the probe round-trip works

## Shared Patterns

- **Route ordering:** `ui.run_with` is called last in `create_app`. This applies to every FastAPI route and router, now and in later phases.
- **No auth:** the link is the capability. Supabase keys stay server-side. RLS is on with no anon/authenticated policies and their grants revoked.
- **Validation parity:** each rule is applied in the UI/service and again in the DB CHECK (token regex, project name 1-100, name 1-40).
- **Error handling:** expected not-found paths return `None`, never exceptions (Pitfall 7). The unique-violation `23505` gets one token-regenerate retry. Use `logger.warning` for expected failures.
- **Secrets:** `SecretStr` everywhere, and never log the settings object or the Realtime URL.
- **Single worker:** hard-coded in the launcher and documented in the README.

## No Analog Found

Everything above, since the repo is greenfield. The thinnest references, which the planner must author from spec rather than from code, are:
- `README.md`: env vars, `supabase db push --linked`, `python -m app`, the single-worker note, which key worked for Realtime, and the `/healthz` meaning.
- `home_page.py`
- `services/sessions.py`
- `health.py`
- `db/client.py`
- `tests/conftest.py`

## Metadata

**Analog search scope:** the whole repo (`git ls-files`, `supabase/`).
**In-repo source files found:** 0.
**Tracked-source gate:** no mirror paths are referenced; all paths are new files.
**Note:** 01-RESEARCH.md lines 609-724 (past the first read page) were not read, so any Validation Architecture or test map detail there is not reflected.
**Pattern extraction date:** 2026-10-22
