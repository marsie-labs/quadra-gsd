# Phase 1: Session Skeleton - Research

**Researched:** 2026-10-22
**Domain:** Python greenfield bootstrap (uv + FastAPI + NiceGUI single worker) on hosted Supabase (schema, RPC, RLS, Realtime Postgres Changes)
**Confidence:** HIGH for stack, NiceGUI patterns, schema/migration SQL (all probed this session); MEDIUM-LOW for one item: whether the hosted Realtime service accepts the new `sb_secret_` key (cannot be verified without the user's key; see A1 and Open Question 1)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Display name prompt
- **D-01:** First-time visitor sees an **inline banner** on the canvas page asking for a display name — NOT a blocking modal and NOT a separate join screen. The canvas (quadrants) is fully visible and usable behind it; the visitor may ignore the banner.
- **D-02:** Every card must have a real author. When an unnamed participant attempts an authoring action (adding a card, Phase 2), the app prompts for the name at that moment and completes the action only after a valid name is given. Phase 1 must expose a reusable "ensure display name, then continue" helper so Phase 2 can call it; no "Anonymous" fallback author exists.
- **D-03:** Display name is **fixed per browser** once set — no rename UI. Changing it requires clearing browser storage. The current name is shown on the canvas page (e.g., header) as read-only text. Name persists across reloads and across different sessions in the same browser (IDEN-02).
- **D-04:** Name rules: whitespace trimmed; empty after trim is rejected; max 40 characters; duplicate names across participants are allowed (no auth by design). Invalid input shows an inline validation message, nothing is saved.

### Claude's Discretion
User chose not to discuss these; planner/researcher pick sensible defaults consistent with research docs:
- **Canvas layout & header** — 2×2 quadrant grid arrangement, header content (project name, current display name), empty-quadrant appearance. Copy-link button is v2 (UX-04) — not required here.
- **Home page** — project name form + create button; project name validation (required, trimmed, sensible max length) at Claude's discretion.
- **Not-found page** — friendly message for unknown `session_id`; a link back to home is reasonable.
- **Startup Realtime check** — behavior on failure (fail fast vs. warn), reporting channel (log and/or `/healthz`). Must make it obvious to a developer whether DB change events reach the server (success criterion 5).
- **Token format** — `session_id` generation (e.g., `secrets.token_urlsafe(16)` or UUIDv4), separate internal PK per research.
- **Name storage mechanism** — research recommends NiceGUI `app.storage.user` with `storage_secret`; any per-browser mechanism meeting D-03 is acceptable.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. (Card add/edit/delete/move, live card sync, close, and the agent API belong to Phases 2–5; copy-link button is v2 / UX-04.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SESS-01 | User creates a session by entering a project name and lands on its unique link | Home page `@ui.page('/')` → `SessionService.create_session` → `create_session` RPC → `ui.navigate.to('/s/<id>')`. Flow prototyped and passing in NiceGUI `user` fixture this session |
| SESS-02 | `session_id` is an unguessable ≥128-bit random token | `secrets.token_urlsafe(16)` = exactly 16 random bytes = 22 chars (verified over 20 000 samples). **UUIDv4 is only 122 random bits and does NOT satisfy ≥128-bit** (see Pitfall 6). DB `CHECK` enforces `^[A-Za-z0-9_-]{22,64}$` |
| SESS-03 | New session starts open with four quadrants IS / IS NOT / DOES / DOES NOT, created atomically | Single plpgsql `create_session` function (one transaction); validated in Postgres 17: 4 quadrants created, failed calls leave no partial rows |
| SESS-04 | Anyone with the link can open it without logging in | No auth; link is the capability. Second-browser test via NiceGUI `create_user` fixture; server uses the secret key, browsers never see Supabase |
| SESS-05 | Unknown session link shows not-found | Page sets `ui.context.client.status_code = 404` and renders a friendly body (real HTTP 404 + custom content, verified) |
| IDEN-01 | First-time visitor is prompted for display name | Inline banner on canvas page (D-01) + reusable `ensure_display_name()` dialog helper (D-02), both prototyped and passing |
| IDEN-02 | Display name remembered across reloads and sessions | `app.storage.user['display_name']` + `storage_secret` + `max_age` extended from the 14-day default (verified `Max-Age=31536000` header) |
| IDEN-03 | Display name recorded as author on cards | No cards written in Phase 1. Deliver: `cards.author` column with `CHECK (char_length(author) between 1 and 40)` (same rule as D-04) + the `ensure_display_name()` helper Phase 2 calls |
| QUAL-04 | App runs locally with documented setup (env vars, migrations, single worker) | `.env.example`, `supabase db push --linked`, `python -m app` launcher with `workers=1` hard-coded (verified), README, startup Realtime round-trip check + `/healthz` |
</phase_requirements>

## Summary

Phase 1 is greenfield: there is no code, no `pyproject.toml`, no `.gitignore`, and no `supabase/config.toml` yet (only `supabase/.temp/` from the CLI link). The work is (a) project scaffold with uv, (b) one Supabase migration (tables, RLS, explicit grants, `create_session` RPC, Realtime publication, a tiny `realtime_probe` table), (c) FastAPI + NiceGUI app factory with three pages (home, canvas, not-found) and the display-name flow, and (d) a `RealtimeHub` skeleton whose startup check writes a probe row through PostgREST and waits for the matching Postgres Changes event, reporting the result in logs and `/healthz`.

I prototyped the risky mechanics in a scratch venv with the real pinned stack (nicegui 3.18.0, supabase 2.33.0, fastapi 0.160.0, starlette 1.9.0, Python 3.12): pages + `app.storage.user` + 404 status + the awaitable name dialog all pass in the NiceGUI `user` fixture; `uvicorn.run(create_app, factory=True, workers=1)` works with `ui.run_with`; and the migration SQL was executed in a throwaway Postgres 17 container (with stubbed Supabase roles) including failure/rollback and permission checks. Three findings change the naive plan: **(1)** FastAPI routes registered *after* `ui.run_with(app)` are shadowed (404) because NiceGUI is mounted at `/`; **(2)** Supabase is changing the default so new `public` tables/functions are *not* auto-granted to `service_role` (new projects since 2026-05-30, all existing projects on 2026-10-30; this project was created 2026-10-22) so the migration must contain explicit grants; **(3)** the only unverifiable risk is Realtime + `sb_secret_` key auth, which the startup check exists to settle on the first run.

**Primary recommendation:** Build Phase 1 as three vertical slices: (1) scaffold + migration + settings, applied to the hosted project behind a human-action checkpoint; (2) service/repository + home/canvas/not-found pages + identity (test with fake service in the `user` fixture); (3) `RealtimeHub` startup probe + `/healthz` + README. Use `workspaces` as the table name, a Python-generated `secrets.token_urlsafe(16)` as `session_id`, `app.storage.user` for the name, explicit service_role grants, and a **strict-by-default** startup check (`warn`/`off` via env).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Create session (name validation, token generation) | API / Backend (SessionService) | Database (RPC, CHECK constraints) | Python generates the token; DB enforces shape and atomicity |
| Atomic workspace + 4 quadrants | Database / Storage (plpgsql function) | — | Multi-step insert must be one transaction; PostgREST `.rpc()` runs one function call in one transaction |
| Session lookup by `session_id` / not-found | API / Backend (SessionService + page) | Database (unique index) | Page decides 404 vs render; DB provides the lookup |
| Render home / canvas / not-found | Frontend Server (NiceGUI, server-driven) | — | NiceGUI renders on the server and pushes diffs; browser holds no Supabase keys |
| Display name capture + persistence | Frontend Server (`app.storage.user`) | Browser (signed session cookie only) | Name lives server-side keyed by cookie session id (D-03) |
| Name validation (trim, 1–40) | API / Backend (pure function) | Database (`cards.author` CHECK) | Same rule at UI and DB so an unnamed/invalid author can never be stored |
| Realtime connection + startup proof | API / Backend (RealtimeHub in FastAPI lifespan) | Database (publication, RLS grants) | Server is the single Realtime subscriber; DB side must publish and authorize events |
| Health reporting | API / Backend (`/healthz`) | — | Makes check outcome observable without reading logs |
| Access control | Database (RLS enabled, no anon/authenticated policies + REVOKE) | API / Backend (secret key server-only) | Link is the capability; DB blocks the publishable key from everything |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 (uv has 3.12.10 installed) | Runtime | Project floor; pydantic-settings needs ≥3.11 [CITED: .claude/CLAUDE.md] |
| fastapi | >=0.159 (PyPI latest 0.160.0, published 2026-10-22) | HTTP app, `/healthz`, host for NiceGUI | User-specified [CITED: .claude/CLAUDE.md]; version [VERIFIED: pypi.org/pypi/fastapi/json] |
| nicegui | >=3.18 (3.18.0) | Server-driven UI | User-specified; `requires_python <4,>=3.10` [VERIFIED: pypi.org/pypi/nicegui/json] |
| supabase | >=2.33 (2.33.0) | Async PostgREST client (+ bundled `realtime`, `postgrest`) | User-specified; resolved `realtime 2.33.0`, `postgrest 2.33.0` [VERIFIED: installed in scratch venv] |
| uvicorn[standard] | >=0.54 (0.54.0) | ASGI server, run single worker | [VERIFIED: pypi.org/pypi/uvicorn/json] |
| pydantic / pydantic-settings | 2.14.1 / 2.16.1 | Models, typed env config | [VERIFIED: PyPI JSON] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 | Test runner | All tests [VERIFIED: PyPI JSON] |
| pytest-asyncio | 1.4.0 | Async tests, needed by NiceGUI `user` fixture | `asyncio_mode = "auto"` [VERIFIED: used in passing prototype] |
| httpx | 0.28.1 | Transport for API tests (already a supabase dep) | Later phases (agent API); `healthz` test now |
| ruff | 0.17.1 | Lint + format | Single tool [VERIFIED: PyPI JSON] |
| Supabase CLI | 2.121.0 (installed, logged in, linked to `fligjsqzjoyedcuolwss`) | Migrations → hosted project | `supabase db push --linked` [VERIFIED: `supabase projects list` output] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `app.storage.user` | `app.storage.browser` (data inside the signed cookie) | Survives deletion of `.nicegui/` on the server, but docs/research recommend `user`; either meets D-03. Stay with `user` |
| `secrets.token_urlsafe(16)` | UUIDv4 | UUIDv4 = 122 random bits, fails the ≥128-bit requirement |
| Hub owns an `AsyncRealtimeClient` | Use `supabase_client.channel()` | Owning the client lets `SUPABASE_REALTIME_KEY` (legacy JWT fallback) differ from the PostgREST key with no monkey-patching. Both work mechanically |
| Probe table | Create/inspect real session rows for the check | Probe avoids polluting `workspaces` and exercises the same RLS+publication path |

**Installation:**
```bash
uv init --bare --python 3.12 --name quadra      # verified: writes only pyproject.toml (requires-python >=3.12)
uv python pin 3.12
uv add "fastapi>=0.159" "nicegui>=3.18" "supabase>=2.33" "uvicorn[standard]>=0.54" "pydantic>=2.14" "pydantic-settings>=2.16"
uv add --dev "pytest>=9.1" "pytest-asyncio>=1.4" httpx ruff
```

**Version verification:** versions above queried from `pypi.org/pypi/<pkg>/json` on 2026-10-22; the resolved set (`nicegui 3.18.0, fastapi 0.160.0, starlette 1.9.0, python-socketio 5.17.0, uvicorn 0.54.0, supabase/realtime/postgrest 2.33.0, pydantic 2.14.1`) was installed together in a scratch venv with no conflicts.

## Package Legitimacy Audit

Seam output (`gsd-tools query package-legitimacy check --ecosystem pypi ...`) returned **SUS for every package**, with reasons only `too-new` (latest release recently published; heuristics key on the newest upload date, e.g. fastapi 0.160.0 was published today) and `unknown-downloads` (PyPI JSON exposes no download counts), plus `no-repository` for `supabase`/`postgrest` (PyPI metadata has no repo URL field populated). These are heuristic artifacts for long-established, user-specified packages; first-release dates below come from PyPI JSON.

| Package | Registry | Age (first release) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|---------------------|-----------|-------------|---------|-------------|
| nicegui | PyPI | 2021-05 (316 releases) | n/a on PyPI | github.com/zauberzeug/nicegui | SUS (too-new, unknown-downloads) | Approved by name via CLAUDE.md; covered by one lockfile checkpoint |
| supabase | PyPI | 2021-10 (111 releases) | n/a | github.com/supabase/supabase-py (via `realtime` metadata) | SUS (too-new, unknown-downloads, no-repository) | Same |
| realtime / postgrest (transitive of supabase) | PyPI | 2021-12 / — | n/a | github.com/supabase/supabase-py | SUS | Transitive; do not pin separately |
| fastapi | PyPI | 2018-12 (356) | n/a | github.com/fastapi/fastapi | SUS (too-new) | Same |
| uvicorn | PyPI | 2017-06 (204) | n/a | github.com/Kludex/uvicorn | SUS (too-new) | Same |
| pydantic | PyPI | 2017-05 (208) | n/a | github.com/pydantic/pydantic | SUS (too-new) | Same |
| pydantic-settings | PyPI | 2019-08 (47) | n/a | github.com/pydantic/pydantic-settings | SUS (too-new) | Same |
| pytest | PyPI | 2010-11 (192) | n/a | github.com/pytest-dev/pytest | SUS (unknown-downloads) | Same |
| pytest-asyncio | PyPI | 2015-04 (76) | n/a | github.com/pytest-dev/pytest-asyncio | SUS (unknown-downloads) | Same |
| httpx | PyPI | 2019-07 (77) | n/a | github.com/encode/httpx | SUS (unknown-downloads) | Same |
| ruff | PyPI | 2022-08 (428) | n/a | github.com/astral-sh/ruff | SUS (too-new) | Same |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** all of the above (heuristic only). All names come from the project's own CLAUDE.md stack table (an authoritative project document, so not `[ASSUMED]`) and were additionally confirmed on PyPI with multi-year release history. **Planner: add ONE `checkpoint:human-verify` task immediately before the first `uv add`/`uv sync`** (confirm the dependency list matches this table; afterwards review `uv.lock` for unexpected additions) rather than one checkpoint per package. No postinstall concept applies to PyPI wheels in this stack.

## Architecture Patterns

### System Architecture Diagram

```
 Browser A / B (no login)                        Developer
   |  GET /  (create)      GET /s/{session_id}     |  uv run python -m app  (workers=1)
   |  socket.io (NiceGUI)                          |  supabase db push --linked
   v                                               v
+------------------------- Python process (uvicorn, 1 worker) --------------------------------+
| FastAPI app (create_app)                                                                    |
|   lifespan: acreate_client -> Repository -> SessionService -> RealtimeHub.start()           |
|             -> startup probe (strict/warn/off) -> yield -> hub.stop(), client close         |
|   GET /healthz  (registered BEFORE ui.run_with)                                             |
|   ui.run_with(app, storage_secret, session max_age)   <- LAST: mounts NiceGUI at "/"        |
|                                                                                             |
|  NiceGUI pages                                                                              |
|   "/"                 project name form --validate--> SessionService.create_session         |
|                                                          |  token = secrets.token_urlsafe(16)|
|                                                          v                                  |
|                         ui.navigate.to("/s/{id}") <--- Repository.rpc("create_session")     |
|   "/s/{session_id}"   format check -> Repository.get_session -> None? -> status 404 page    |
|                       else header(project, name|banner) + 2x2 grid of 4 quadrants           |
|                       name banner / ensure_display_name() --> app.storage.user["display_name"]|
|                                                                                             |
|  RealtimeHub (AsyncRealtimeClient, 1 channel "quadra-db")                                   |
|   bindings: realtime_probe (*), workspaces (INSERT)   [Phase 2 adds cards, resync]          |
|   startup probe: upsert probe row (nonce) --PostgREST--> DB ... CDC event --WS--> callback  |
+-----------------|-----------------------------------------------^---------------------------+
                  | HTTPS (PostgREST, secret key, apikey header)  | WSS (Realtime, ?apikey=...)
                  v                                               |
+------------------------------ Supabase (hosted, ref fligjsqzjoyedcuolwss) ------------------+
|  workspaces / quadrants / cards / realtime_probe   (RLS ON, no policies, anon+auth REVOKED) |
|  create_session(p_project_name, p_session_id)  (EXECUTE: service_role only)                 |
|  publication supabase_realtime: workspaces, cards, realtime_probe;  cards REPLICA IDENT FULL|
+---------------------------------------------------------------------------------------------+
```

### Recommended Project Structure
```
quadra-gsd/                     # repo root (pyproject.toml here)
├── app/
│   ├── __init__.py
│   ├── __main__.py             # python -m app  -> uvicorn.run(create_app, factory=True, workers=1)
│   ├── main.py                 # create_app(): FastAPI + lifespan + routes + ui.run_with (LAST)
│   ├── settings.py             # pydantic-settings
│   ├── deps.py                 # module-level Services container set in lifespan (tests set fakes)
│   ├── models.py               # SessionView, QuadrantView, QUADRANT_LABELS
│   ├── tokens.py               # new_session_id(), SESSION_ID_RE
│   ├── db/
│   │   ├── client.py           # acreate_client factory
│   │   └── repository.py       # create_session(), get_session(), upsert_probe()
│   ├── services/
│   │   └── sessions.py         # SessionService (validation + repo orchestration)
│   ├── realtime/
│   │   └── hub.py              # RealtimeHub + startup probe + status for /healthz
│   └── ui/
│       ├── home_page.py        # "/"
│       ├── canvas_page.py      # "/s/{session_id}" + not-found branch
│       └── identity.py         # validate_display_name(), current_name(), ensure_display_name()
├── supabase/
│   ├── config.toml             # from `supabase init` (major_version = 17)
│   └── migrations/20261022000000_init_schema.sql
├── tests/
│   ├── unit/                   # tokens, name validation, settings, hub dispatch w/ fake messages
│   ├── ui/                     # NiceGUI user fixture; ui_main.py harness registers pages w/ fake service
│   └── integration/            # @pytest.mark.integration: real Supabase (RPC, RLS, probe roundtrip)
├── .env.example  .gitignore  README.md  pyproject.toml  uv.lock  .python-version
```

`.gitignore` must include (none exists today): `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.env`, `.nicegui/` (NiceGUI default storage dir, see Pitfall 8), `supabase/.temp/` (STATE.md note; `supabase init` does not create a `supabase/.gitignore` in CLI 2.121.0 — verified, only `config.toml` was produced).

### Pattern 1: App factory with strict ordering
**What:** `create_app()` builds FastAPI, registers every plain FastAPI route and router, registers NiceGUI pages, and calls `ui.run_with(app, ...)` **last**. Launch via `python -m app` (single worker in code) or `uvicorn app.main:create_app --factory`.
**When to use:** Always, including Phase 2–5 (the `/api/sessions/{id}/results` router must also be included before `run_with`).
**Evidence:** a route added after `run_with` returned 404 on a live server while the one added before returned 200 [VERIFIED: probe in scratch, uvicorn log `http://localhost:8765/after not found`]; NiceGUI mounts itself with `app.mount(mount_path, core.app)` at `/` [VERIFIED: nicegui/ui_run_with.py]. The FastAPI `lifespan` passed to `FastAPI(lifespan=...)` runs and NiceGUI's `_startup()`/`_shutdown()` wrap it [VERIFIED: ui_run_with.py `lifespan_wrapper`, and `app.state.hub` populated in probe].

### Pattern 2: Dependency container instead of globals in pages
**What:** `app/deps.py` exposes `services: Services | None`; lifespan assigns the real object; the UI-test harness assigns fakes before `ui.run(...)`. Pages call `deps.services.sessions...`.
**Why:** The NiceGUI `user` fixture does **not** run the outer FastAPI lifespan (it runs `core.app.router.lifespan_context(core.app)` only [VERIFIED: nicegui/testing/user_simulation.py]), so UI tests never touch Supabase or the hub unless they set them up deliberately.

### Pattern 3: Not-found as a real 404 with custom body
```python
# Source: verified in scratch prototype; client.status_code is a public attribute
# [VERIFIED: nicegui/client.py:125 `self.status_code: int = 200`; nicegui/page.py:233 build_response(request, client.status_code)]
ui.context.client.status_code = 404
ui.label('Session not found'); ui.link('Create a new session', '/')
```
In tests `user.open()` asserts status 200 [VERIFIED: nicegui/testing/user.py:72], so assert 404 with `await user.http_client.get(path)` (used in prototype) instead.

### Pattern 4: Hub as the only Realtime owner, callbacks never block
`AsyncRealtimeChannel._handle_message` calls each postgres-changes callback **synchronously** inside the socket listen loop (`for postgres_callback in self.postgres_changes_callbacks: postgres_callback(payload)` [VERIFIED: realtime/_async/channel.py:566-568]). Callbacks must be plain `def` that only set a future / put on a queue / `create_task`.

### Pattern 5: Name capture
Banner on the page for display + `ensure_display_name()` awaitable dialog for authoring actions (code in Code Examples; both exercised by passing `user` tests). Single `validate_display_name()` pure function shared by banner, dialog and tests.

### Anti-Patterns to Avoid
- **`ui.run_with` before routes/routers** — later routes silently 404.
- **`ui.html`/`ui.markdown` for user-provided text** — use `ui.label`. (`ui.html` default `sanitize=True` in 3.18 [VERIFIED: signature printed], but avoid anyway.)
- **Awaiting slow work in a page with the default `response_timeout=3.0`** — NiceGUI returns an error page after 3 s [VERIFIED: nicegui/page.py "took longer than the response_timeout"]. Set `response_timeout=10` on the canvas page.
- **Python-side two-step create (workspace then quadrants)** — non-atomic; use the RPC.
- **Granting `anon`/`authenticated` anything** — see Security Domain.
- **Logging the Realtime URL / enabling DEBUG on `realtime` or `websockets`** — the key is in the URL query (`wss://.../websocket?apikey=<key>` [VERIFIED: realtime/_async/client.py:78-79 and printed `c.url`]).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-browser persistent storage | Custom cookies/localStorage JS | `app.storage.user` + `storage_secret` | Signed session cookie → server-side file store; verified persistence across reloads in tests |
| Random unguessable id | `random`, uuid4, timestamp hash | `secrets.token_urlsafe(16)` | CSPRNG, exactly 128 bits |
| Atomic multi-row create | Sequential PostgREST inserts | plpgsql `create_session` via `.rpc()` | Single transaction, verified rollback |
| Env/config parsing | `os.environ` plumbing | `pydantic-settings` (`SecretStr` for keys) | Typed, validated, secrets masked in repr |
| 404 page plumbing | Custom Starlette exception handlers | `client.status_code = 404` in the page | Keeps NiceGUI layout/storage working |
| Realtime reconnect/backoff | Own websocket client | `realtime` (bundled) with `auto_reconnect=True` | Existing exponential backoff; Phase 2 adds resync |
| Migrations/versioning | Ad-hoc SQL in dashboard | `supabase/migrations/*.sql` + `supabase db push --linked` | Reproducible, README-able |
| HTTP/UI test driving | Selenium/Playwright | NiceGUI `user` fixture | Headless, <1 s per test |

**Key insight:** every "obvious" custom solution here collides with a pitfall already designed around (non-atomic create, guessable ids, silent Realtime failure); use the platform pieces and spend effort on the proof (round-trip probe).

## Common Pitfalls

### Pitfall 1: Routes registered after `ui.run_with` return 404
**What goes wrong:** `/healthz` (and later `/api/...`) work in unit tests but 404 on the real server.
**Why:** NiceGUI is mounted at `/` and shadows later routes [VERIFIED: probe].
**How to avoid:** factory ordering (Pattern 1). Add a `/healthz` test via `httpx.ASGITransport(create_app(...))` for the *real* factory with fake settings/services.
**Warning signs:** HTML 404 from NiceGUI at an API path.

### Pitfall 2: New tables/functions are not granted to `service_role`
**What goes wrong:** App starts, every PostgREST call returns `42501 permission denied`, Realtime delivers nothing.
**Why:** Supabase's auto-grant default is being switched off: new projects since 2026-05-30, existing projects on 2026-10-30 [CITED: supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically]. This project was created 2026-10-22 [VERIFIED: `supabase projects list` → `created_at`], so assume opt-in grants. `supabase/config.toml` even documents `auto_expose_new_tables` [VERIFIED: `supabase init` output].
**How to avoid:** explicit `grant select, insert, update, delete ... to service_role` and `grant execute ... to service_role` in the migration (harmless if auto-grants still exist).
**Warning signs:** error code `42501` with a GRANT hint from PostgREST.

### Pitfall 3: Function EXECUTE defaults to everyone
**What goes wrong:** the publishable (public) key can call `rpc('create_session')` and create spam sessions.
**Why:** "By default, any role can run a database function" [CITED: supabase.com/docs/guides/database/functions]; Supabase default privileges also grant EXECUTE directly to `anon`/`authenticated` [CITED: supabase.com/docs/guides/api/hardening-data-api].
**How to avoid:** `revoke execute on function ... from public, anon, authenticated;` then `grant ... to service_role` (validated: `anon` got `permission denied for function create_session`).

### Pitfall 4: RLS-on tables + Realtime Postgres Changes authorizes each event per subscriber
**What goes wrong:** channel reports SUBSCRIBED, but no events arrive.
**Why:** "Postgres Changes authorizes every event against each subscriber" [CITED: supabase.com/docs/guides/realtime/postgres-changes]. A subscriber whose role is not `service_role`/BYPASSRLS sees nothing with deny-all RLS. The docs state secret keys map to `service_role`, which has BYPASSRLS [CITED: supabase.com/docs/guides/api/api-keys], but nothing in the fetched docs says the **Realtime WebSocket** honors `sb_secret_` (Open Question 1 / A1).
**How to avoid:** the startup probe is the proof; fallback is `SUPABASE_REALTIME_KEY` = legacy `service_role` JWT (realtime-py README: `API_KEY` is "a JWT whose claims must contain `exp` and `role`" [CITED: github.com/supabase/supabase-py src/realtime/README.md]).
**Warning signs:** `SUBSCRIBED` then probe timeout; `CHANNEL_ERROR`/`TIMED_OUT` states.

### Pitfall 5: SUBSCRIBED does not prove CDC is flowing
**What goes wrong:** the check passes the subscribe step but the first write is missed.
**Why:** subscription join acknowledgment and replication readiness are separate [ASSUMED]; `replication_ready` exists only as a broadcast config flag in realtime-py [VERIFIED: realtime/types.py:191-195] and I could not confirm its semantics, so do not rely on it (CLAUDE.md's "`replication_ready` system event" claim is unverified).
**How to avoid:** the probe loop re-upserts every ~3 s until the matching nonce arrives or the timeout (default 15 s) elapses.

### Pitfall 6: UUIDv4 does not satisfy "≥128-bit"
UUIDv4 carries 122 random bits. Use 16 random bytes (`token_urlsafe(16)`, 22 chars). Unit test: decode to ≥16 bytes, match `^[A-Za-z0-9_-]{22,64}$`, 1000 samples unique. The DB regex rejects shorter tokens [VERIFIED: Postgres 17 run, `short` rejected by `workspaces_session_id_check`].

### Pitfall 7: `maybe_single().execute()` returns `None` (not an empty response) when no row
[VERIFIED: postgrest/_async/request_builder.py:162-170: `if len(parsed.data) == 0: return None`]. Code that does `resp.data` on an unknown `session_id` raises `AttributeError` → 500 instead of the not-found page. Handle `None` explicitly.

### Pitfall 8: Storage secret and storage dir
`storage_secret` must be stable and required (changing it invalidates every cookie → everyone is re-prompted). User data is persisted under `.nicegui/` (env `NICEGUI_STORAGE_PATH`, default `.nicegui` [VERIFIED: nicegui/storage.py:84]); gitignore it. Starlette's session cookie defaults to a 14-day `max_age` [VERIFIED: starlette/middleware/sessions.py:22]; pass `session_middleware_kwargs={'max_age': 365*24*3600}` (verified `Max-Age=31536000` on a live server) so IDEN-02 "remembered" holds beyond two weeks.

### Pitfall 9: Async page + DB await + `response_timeout`
Default `response_timeout=3.0`. Use `@ui.page('/s/{session_id}', response_timeout=10)`. Reading `app.storage.user` after an `await` inside the page worked in tests and on a live server (probe).

### Pitfall 10: NiceGUI `user` fixture fails the test on any ERROR log
[VERIFIED: nicegui/testing/user_plugin.py `if logs: pytest.fail('There were unexpected ERROR logs.')`]. Don't `logger.error` in expected-failure paths exercised by UI tests (use `warning`).

### Pitfall 11: Secret key in logs/URLs
realtime-py puts the key in the WS URL and (in the versions that predate its redaction fix) can log it at DEBUG. Keep `realtime`/`websockets` loggers ≥ INFO, never log the settings object (use `SecretStr`), and `.env` stays gitignored.

### Pitfall 12: 24-hour connection cap for secret-key Realtime connections
"Connections last 24 hours when there's no signed in user, or when using a secret key" [CITED: github.com/orgs/supabase/discussions/29260]. Not a Phase 1 failure, but the hub must treat a server-initiated close as normal and Phase 2's resync-on-resubscribe is mandatory. realtime-py handles `ConnectionClosedError` with auto-reconnect and `max_retries=5`; its `ConnectionClosedOK` branches are separate [VERIFIED: realtime/_async/client.py:121,271-273]. Reconnect-after-24h behavior is unverified (A8) — carry into Phase 2 research.

## Code Examples

### Migration `supabase/migrations/20261022000000_init_schema.sql`
Executed end-to-end in `postgres:17-alpine` with stub roles (`anon`, `authenticated`, `service_role bypassrls`) and an empty `supabase_realtime` publication: created cleanly; `create_session('  Acme  ', 'abcdefghijklmnopqrstuv')` returned the id, trimmed the name, produced 4 quadrants (IS/IS_NOT/DOES/DOES_NOT, positions 1–4); duplicate token → `23505`; short token and empty name → check violations with no partial rows; `anon`/`authenticated` → `permission denied`; publication lists `cards, realtime_probe, workspaces`; `cards` `relreplident = f` (full). Not run against the hosted project.
```sql
create type public.workspace_status as enum ('open', 'closed');
create type public.quadrant_kind as enum ('IS', 'IS_NOT', 'DOES', 'DOES_NOT');

create table public.workspaces (
  id           uuid primary key default gen_random_uuid(),
  session_id   text not null unique
               check (session_id ~ '^[A-Za-z0-9_-]{22,64}$'),
  project_name text not null
               check (char_length(project_name) between 1 and 100),
  status       public.workspace_status not null default 'open',
  created_at   timestamptz not null default now(),
  closed_at    timestamptz,
  closed_by    text check (closed_by is null or char_length(closed_by) between 1 and 40),
  constraint workspaces_closed_consistent
    check ((status = 'closed') = (closed_at is not null))
);

create table public.quadrants (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  kind         public.quadrant_kind not null,
  position     smallint not null check (position between 1 and 4),
  unique (workspace_id, kind),
  unique (workspace_id, position),
  unique (id, workspace_id)
);

create table public.cards (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.workspaces (id) on delete cascade,
  quadrant_id   uuid not null,
  text          text not null check (char_length(btrim(text)) between 1 and 500),
  order_index   double precision not null,
  author        text not null check (char_length(author) between 1 and 40),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  deleted_at    timestamptz,
  foreign key (quadrant_id, workspace_id)
    references public.quadrants (id, workspace_id)   -- card can only sit in a quadrant of its own session
);
create index cards_workspace_id_idx on public.cards (workspace_id);
create index cards_quadrant_order_idx
  on public.cards (quadrant_id, order_index, created_at, id) where deleted_at is null;

create table public.realtime_probe (
  id        smallint primary key default 1 check (id = 1),
  nonce     text not null,
  pinged_at timestamptz not null default now()
);

alter table public.workspaces     enable row level security;
alter table public.quadrants      enable row level security;
alter table public.cards          enable row level security;
alter table public.realtime_probe enable row level security;

revoke all on table public.workspaces, public.quadrants, public.cards, public.realtime_probe
  from anon, authenticated;
grant select, insert, update, delete
  on table public.workspaces, public.quadrants, public.cards, public.realtime_probe
  to service_role;

create function public.create_session(p_project_name text, p_session_id text)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_workspace_id uuid;
begin
  insert into public.workspaces (session_id, project_name)
  values (p_session_id, btrim(p_project_name))
  returning id into v_workspace_id;

  insert into public.quadrants (workspace_id, kind, position)
  select v_workspace_id, q.kind, q.position
  from (values
    ('IS'::public.quadrant_kind, 1),
    ('IS_NOT', 2),
    ('DOES', 3),
    ('DOES_NOT', 4)
  ) as q (kind, position);

  return p_session_id;
end;
$$;

revoke execute on function public.create_session(text, text) from public, anon, authenticated;
grant  execute on function public.create_session(text, text) to service_role;

alter table public.cards replica identity full;   -- Phase 3 needs old quadrant on moves

do $$
declare t text;
begin
  foreach t in array array['workspaces', 'cards', 'realtime_probe'] loop
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;
```
Notes: the final `foreach` publication block (the exact text above) was also executed on Postgres 17 and publishes `cards, realtime_probe, workspaces`. `close_session` and the closed-lock/one-way-status triggers are intentionally deferred to Phase 4 (migrations are append-only; `status/closed_at/closed_by` columns exist now so no later `ALTER`). Phase 4 must also block `DELETE` on cards of closed sessions because `service_role` has DELETE.

### Token and name validation (pure, unit-testable)
```python
# app/tokens.py  -- 22 chars, 128 bits, matches DB CHECK  [VERIFIED: 20000 samples: len==22, charset ok, all unique, decodes to 16 bytes]
import re, secrets
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
def new_session_id() -> str:
    return secrets.token_urlsafe(16)

# app/ui/identity.py
MAX_NAME = 40
def validate_display_name(raw: str | None) -> str | None:
    name = (raw or "").strip()
    return name if 1 <= len(name) <= MAX_NAME else None
```

### Repository (supabase-py 2.33 async)
```python
# Source: signatures read from installed postgrest/supabase 2.33.0
from postgrest.exceptions import APIError
async def get_session(client, session_id: str):
    resp = await (client.table("workspaces")
                  .select("id, session_id, project_name, status, quadrants(id, kind, position)")
                  .eq("session_id", session_id).maybe_single().execute())
    return None if resp is None else resp.data          # None, not an empty response  [VERIFIED request_builder.py:162-170]

async def create_session(client, project_name: str, session_id: str) -> str:
    resp = await client.rpc("create_session", {"p_project_name": project_name, "p_session_id": session_id}).execute()
    return resp.data                                    # scalar text
# On APIError with code == "23505" (unique violation) regenerate token and retry once.
```
The embedded `quadrants(...)` select relies on the FK from `quadrants.workspace_id`; confirm it returns 4 rows in the first integration test. Sort by `position` in Python.

### Realtime hub: subscribe + probe (shape verified offline, live behavior pending)
Offline verification: feeding a `postgres_changes` JSON message through `ServerMessageAdapter.validate_json` and `channel._handle_message` delivered a **plain `dict`** payload: `payload["data"]["type"]` is `RealtimePostgresChangesListenEvent.Update` (a `str` Enum, so `== "UPDATE"` is True), `payload["data"]["record"]` is the new row, `["table"]`, `["commit_timestamp"]`, `["old_record"]` available [VERIFIED: realtime/types.py:94-107 + scratch run]. This is the pattern for hub unit tests with fake events (set `callback.id` as the join reply would).
```python
# app/realtime/hub.py (sketch)
import asyncio, secrets, time
from realtime import AsyncRealtimeClient
from realtime.types import RealtimePostgresChangesListenEvent as Ev, RealtimeSubscribeStates as St

class RealtimeHub:
    def __init__(self, supabase_url: str, key: str):
        self._rt = AsyncRealtimeClient(f"{supabase_url.rstrip('/')}/realtime/v1", token=key)  # https URL accepted -> wss  [VERIFIED]
        self._waiters: dict[str, asyncio.Future] = {}
        self.state = "pending"; self.error: str | None = None; self.latency_ms: float | None = None

    def _on_probe(self, payload) -> None:                     # plain def: runs inside the socket listen loop
        rec = payload["data"].get("record") or {}
        if (fut := self._waiters.get(rec.get("nonce"))) and not fut.done():
            fut.set_result(time.monotonic())

    async def start(self, timeout: float = 15.0) -> None:
        ready: asyncio.Future = asyncio.get_running_loop().create_future()
        ch = self._rt.channel("quadra-db")                    # topic becomes "realtime:quadra-db"
        ch.on_postgres_changes(Ev.All, self._on_probe, table="realtime_probe", schema="public")
        ch.on_postgres_changes(Ev.Insert, self._on_workspace, table="workspaces", schema="public")  # Phase 2 adds cards + registry
        def on_state(state: St, err):                          # also fires again on re-join (Phase 2: resync here)
            if not ready.done():
                (ready.set_result(None) if state is St.SUBSCRIBED
                 else ready.set_exception(RuntimeError(f"{state.value}: {err}")))
        await ch.subscribe(on_state)                          # connect() retries 5x with backoff, then raises
        await asyncio.wait_for(ready, timeout)

    async def verify_roundtrip(self, write_probe, timeout: float = 15.0, resend_every: float = 3.0) -> float:
        nonce = secrets.token_hex(8); fut = asyncio.get_running_loop().create_future(); self._waiters[nonce] = fut
        t0 = time.monotonic()
        try:
            while True:
                await write_probe(nonce)                      # repo.upsert_probe -> PostgREST upsert id=1
                try:
                    await asyncio.wait_for(asyncio.shield(fut), resend_every); break
                except TimeoutError:
                    if time.monotonic() - t0 > timeout: raise
        finally:
            self._waiters.pop(nonce, None)
        return (fut.result() - t0) * 1000
```
`RealtimeSubscribeStates` members: `SUBSCRIBED`, `TIMED_OUT`, `CLOSED`, `CHANNEL_ERROR` [VERIFIED: realtime/types.py:59-63]. `on_postgres_changes(event, callback, table=None, schema=None, filter=None, select=None)` — **callback is the 2nd positional parameter** [VERIFIED: realtime/_async/channel.py:372-380]. `subscribe()` may be called once per channel instance [VERIFIED: channel.py:187-190], so all bindings (Phase 2's `cards`) must be added before it. The subscribe callback also reports `CHANNEL_ERROR` with "mismatch between server and client bindings for postgres changes" if the server's returned bindings differ [VERIFIED: channel.py:240-255]; treat that as a startup failure.

Probe upsert: `client.table("realtime_probe").upsert({"id": 1, "nonce": nonce}).execute()` (first call = INSERT event, later = UPDATE; listener is `*`). Include a `pinged_at` update (`now()`) is optional.

Startup modes (`REALTIME_CHECK`): `strict` (default: failure raises in lifespan → process exits with a clear message listing the stage: connect / subscribe / no-event-timeout and the two most likely fixes), `warn` (log ERROR, continue, `/healthz` shows failed), `off` (tests). `/healthz` returns `{"status": "ok", "realtime": {"state": "verified|failed|disabled|pending", "latency_ms": ..., "error": ...}}` and is registered before `run_with`.

### App factory + launcher
```python
# app/main.py
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(lifespan=make_lifespan(settings), title="Quadra")
    app.include_router(health_router)            # every FastAPI route/router BEFORE run_with
    register_pages()                              # @ui.page('/'), @ui.page('/s/{session_id}', response_timeout=10)
    ui.run_with(app, title="Quadra",
                storage_secret=settings.storage_secret.get_secret_value(),
                session_middleware_kwargs={"max_age": 365 * 24 * 3600})   # LAST
    return app

# app/__main__.py   [VERIFIED: uvicorn.run(create_app, factory=True, workers=1) serves NiceGUI + custom routes]
import uvicorn
from app.main import create_app
if __name__ == "__main__":
    uvicorn.run(create_app, factory=True, host="127.0.0.1", port=8080, workers=1)
```

### Canvas page skeleton and name flow
```python
@ui.page("/s/{session_id}", response_timeout=10)
async def canvas(session_id: str):
    view = await deps.services.sessions.get(session_id)   # format-check first: SESSION_ID_RE, else None without a DB call
    if view is None:
        ui.context.client.status_code = 404
        ui.label("Session not found"); ui.link("Create a new session", "/"); return
    ui.label(view.project_name).classes("text-h5")
    name_label = ui.label(current_name() or "")           # read-only (D-03)
    # banner only when current_name() is None; on save -> app.storage.user["display_name"] = n; banner.clear(); name_label.text = n
    with ui.grid().classes("grid-cols-1 md:grid-cols-2 gap-4 w-full"):
        for q in sorted(view.quadrants, key=lambda q: q.position):
            with ui.card().mark(f"quadrant-{q.kind}"):
                ui.label(QUADRANT_LABELS[q.kind]).classes("text-h6")
                ui.label("No cards yet").classes("text-grey")
```
`ensure_display_name()` (Phase 2 calls it before every authoring action): returns the stored name immediately, else opens a `ui.dialog`, validates with `validate_display_name`, writes `app.storage.user['display_name']`, and `dialog.submit(name)`; Cancel submits `None` so the caller aborts the action. Verified flow in the `user` fixture: empty → inline error "Name is required (max 40 characters)" → valid name → action completes → second call shows no dialog. `QUADRANT_LABELS = {"IS": "IS", "IS_NOT": "IS NOT", "DOES": "DOES", "DOES_NOT": "DOES NOT"}`.

### Test harness (verified pattern)
```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
main_file = "tests/ui/ui_main.py"          # nicegui 'user' fixture runs this via runpy
addopts = "-p nicegui.testing.user_plugin -m 'not integration'"
markers = ["integration: needs real Supabase (SUPABASE_URL/SECRET_KEY) - run with -m integration"]
```
```python
# tests/ui/ui_main.py
from app import deps
from app.ui.pages import register_pages
deps.services = FakeServices()            # in-memory SessionService stand-in
register_pages()
from nicegui import ui
ui.run(storage_secret="test")
```
Second browser: `create_user` fixture (shipped in `nicegui/testing/user_plugin.py`) yields a fresh `User` with its own cookies.

### Dotenv
```
# .env.example
SUPABASE_URL=https://fligjsqzjoyedcuolwss.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...            # server only; never expose to browsers
# SUPABASE_REALTIME_KEY=eyJ...               # optional: legacy service_role JWT if Realtime rejects the sb_secret_ key
STORAGE_SECRET=change-me-long-random         # required; keep stable or users are re-prompted for their name
APP_BASE_URL=http://localhost:8080
REALTIME_CHECK=strict                        # strict | warn | off
```
`Settings(BaseSettings)` with `SecretStr` fields and `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`; `storage_secret` has no default.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Auto-grant new `public` tables/functions to `anon/authenticated/service_role` | Opt-in explicit GRANTs | New projects 2026-05-30; existing projects 2026-10-30 [CITED: supabase changelog 45329] | Migration needs explicit `grant ... to service_role` |
| Legacy `anon`/`service_role` JWT keys | `sb_publishable_` / `sb_secret_` (non-JWT) | Legacy deprecated by end of 2026 [CITED: .claude/CLAUDE.md] | Realtime acceptance unproven; fallback env var |
| NiceGUI auto-index / script mode | `@ui.page` functions only | NiceGUI 3.0 | Already in stack constraints |
| supabase-py `maybe_single()` raising / returning empty response | Returns `None` when no row (2.33) | current | Pitfall 7 |

**Deprecated/outdated:** UUIDv4 as a ≥128-bit token (122 bits); `ui.run()` for hosting (use `ui.run_with`); sync `create_client` for Realtime.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The hosted Realtime WebSocket accepts an `sb_secret_` key in `?apikey=` and authorizes Postgres Changes as `service_role` (RLS bypass). Docs only confirm key→role mapping for the Data API | Pitfall 4, Summary | Startup probe times out; fallback to legacy JWT via `SUPABASE_REALTIME_KEY`. Cost: one config change, but the default `.env.example` may need flipping |
| A2 | Table is named `workspaces` (per ARCHITECTURE.md) although CONTEXT.md loosely says "sessions/quadrants/cards"; public token column stays `session_id` | Standard Stack / Migration | Naming churn in later phases if user expected `sessions`; recommend confirm during plan review (cheap: rename before first push) |
| A3 | `SUBSCRIBED` can precede CDC readiness, hence the re-upsert loop | Pitfall 5 | Loop is harmless if wrong |
| A4 | `replication_ready` broadcast option is not needed/understood | Pitfall 5 | None (we don't use it) |
| A5 | `supabase db push --linked` works without an interactive DB password under CLI 2.121.0 (binary strings mention a minted login role and `SUPABASE_DB_PASSWORD`); not executed this session | Environment Availability | README step may need `SUPABASE_DB_PASSWORD` or `-p`; fallback: paste the SQL in the dashboard SQL editor |
| A6 | Strict-by-default startup check is the preferred failure mode (user left it to Claude) | Summary | If user prefers warn-and-continue, flip default; one env var |
| A7 | After a 24 h cap / server-initiated close, realtime-py re-joins automatically | Pitfall 12 | Phase 2 hub resilience; out of Phase 1 scope |
| A8 | Postgres Changes subscribe to a table missing from the publication fails silently or with CHANNEL_ERROR (unknown which) | Hub | Probe times out either way; message wording differs |
| A9 | `notify pgrst, 'reload schema'` after DDL is unnecessary on hosted Supabase (auto-reload on DDL); adding it at the end of the migration is harmless | Migration | Stale schema cache → first RPC returns PGRST202; just add the NOTIFY if seen |

## Open Questions

1. **Does hosted Realtime accept the new `sb_secret_` key for Postgres Changes?**
   - Known: key maps to `service_role` (BYPASSRLS) for the Data API; connections capped at 24 h; no official statement for the Realtime WS; realtime-py has no client-side JWT check, key goes straight into `?apikey=`.
   - Unclear: server-side acceptance and role mapping on the WS.
   - Recommendation: Plan a `checkpoint:human-action` (user supplies keys in `.env`, runs `supabase db push --linked`, starts the app). The strict startup check settles it; if it fails, user sets `SUPABASE_REALTIME_KEY` (legacy `service_role` JWT from dashboard) and README records which key worked. I did not fetch or use the user's keys.
2. **`workspaces` vs `sessions` table name** (A2). Recommendation: keep `workspaces` + `session_id`; confirm at plan review.
3. **Human steps requiring the user:** creating `.env` with secrets; `supabase db push --linked` (mutates hosted DB). Mark both as checkpoints.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | project/env mgmt | ✓ | 0.7.9 | — |
| Python 3.12 | runtime | ✓ via uv | 3.12.10 (uv-managed); default `python3` is 3.11.11, pyenv `python3.12` shim is broken | `uv python pin 3.12` (uses uv-managed install) |
| Supabase CLI | migrations | ✓ | 2.121.0, logged in, linked to `fligjsqzjoyedcuolwss` (project `quadra-gsd`, us-east-1, Postgres 17.11, ACTIVE_HEALTHY) | Paste migration SQL in dashboard SQL editor |
| Hosted Supabase REST/Realtime reachability | integration + app | ✓ | HTTP 401 without key on `/rest/v1/` and `/realtime/v1/api/ping` (reachable) | — |
| Supabase keys (`sb_secret_`, optional legacy JWT) | app + integration tests | ✗ not in repo (no `.env`) | — | User must provide (checkpoint) |
| Docker | optional local Postgres/`supabase start` | ✓ | 29.9.1 (daemon running; `postgres:17-alpine` pulled during research) | Not required |
| psql | ad-hoc SQL | ✗ | — | Supabase CLI / dashboard SQL editor |
| Node | not needed | ✓ | 22.14.0 | — |

**Missing dependencies with no fallback:** Supabase keys in a local `.env` (user action).
**Missing dependencies with fallback:** psql (use CLI/dashboard).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1 + pytest-asyncio 1.4 (`asyncio_mode=auto`) + `nicegui.testing.user_plugin` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (none exists; Wave 0) |
| Quick run command | `uv run pytest -q` (excludes `integration` marker by default; prototype of 4 UI tests ran in 0.7 s) |
| Full suite command | `uv run pytest -q -m "integration or not integration"` with `.env` present (adds real-Supabase tests) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SESS-01 | Home form validates, creates, lands on `/s/<id>` | ui (fake service) | `uv run pytest tests/ui/test_home.py -q` | ❌ Wave 0 |
| SESS-02 | Token ≥16 bytes, charset, uniqueness; DB rejects short token | unit + integration | `uv run pytest tests/unit/test_tokens.py -q`; `-m integration tests/integration/test_create_session.py` | ❌ Wave 0 |
| SESS-03 | RPC returns id, 4 quadrants, atomic on failure | integration | `uv run pytest -m integration tests/integration/test_create_session.py -q` | ❌ Wave 0 |
| SESS-04 | Second user (no login) sees same project + 4 quadrants | ui (`create_user`) | `uv run pytest tests/ui/test_canvas.py -q` | ❌ Wave 0 |
| SESS-05 | Unknown/malformed id → HTTP 404 + friendly body, no DB call for malformed | ui (`http_client.get`) | `uv run pytest tests/ui/test_not_found.py -q` | ❌ Wave 0 |
| IDEN-01 | New visitor sees banner; canvas visible behind it | ui | `uv run pytest tests/ui/test_identity.py -q` | ❌ Wave 0 |
| IDEN-02 | Name persists after reload and on another session in same browser; header shows it, no rename UI | ui | same | ❌ Wave 0 |
| IDEN-03 | `validate_display_name` (trim/empty/40/duplicates ok); `ensure_display_name` blocks then completes; `cards.author` CHECK | unit + ui + integration | `uv run pytest tests/unit/test_identity.py tests/ui/test_ensure_name.py -q` | ❌ Wave 0 |
| QUAL-04 | Settings load/require secrets; `/healthz`; hub dispatch with fake messages; probe round-trip against real DB | unit + integration | `uv run pytest tests/unit -q`; `-m integration tests/integration/test_realtime_probe.py` | ❌ Wave 0 |
| QUAL-04 (docs) | README steps reproduce from clean clone | manual | follow README once (human verify, end of phase) | manual-only: needs user's keys |

### Sampling Rate
- **Per task commit:** `uv run pytest -q`
- **Per wave merge:** `uv run pytest -q` + `uv run ruff check . && uv run ruff format --check .`
- **Phase gate:** full suite incl. `-m integration` green against hosted project, then `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` with pytest config above, `uv.lock`, `.python-version`
- [ ] `tests/ui/ui_main.py` harness + `FakeServices`; `tests/conftest.py` (env fixtures, integration skip when env missing)
- [ ] `tests/unit/test_tokens.py`, `test_identity.py`, `test_settings.py`, `test_hub_dispatch.py` (fake `ServerMessageAdapter` messages)
- [ ] `tests/ui/test_home.py`, `test_canvas.py`, `test_not_found.py`, `test_identity.py`, `test_ensure_name.py`
- [ ] `tests/integration/test_create_session.py`, `test_realtime_probe.py`, `test_rls_denies_anon.py` (needs publishable key; optional `SUPABASE_PUBLISHABLE_KEY` env, skip if absent); cleanup via service-role DELETE of created `workspaces` (cascade)

## Security Domain

`security_enforcement` is enabled (absent = enabled); `security_asvs_level: 1`, `security_block_on: high`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (by design: link-based, no accounts) | Documented trade-off; display name is a label, not identity |
| V3 Session Management | yes (NiceGUI storage cookie) | Starlette `SessionMiddleware` signed cookie via `storage_secret`; `httponly; samesite=lax` [VERIFIED live `set-cookie` header]; set `https_only=True` when ever served over TLS |
| V4 Access Control | yes | Possession of the unguessable `session_id` is the capability; RLS on, no anon/authenticated policies, table + EXECUTE privileges revoked from `anon/authenticated/public`; no session listing endpoint |
| V5 Input Validation | yes | `validate_display_name`, project-name validator (1–100 after trim), `SESSION_ID_RE` pre-filter before DB, DB `CHECK`s (defense in depth); PostgREST parameterizes (no string SQL built) |
| V6 Cryptography | yes | `secrets.token_urlsafe(16)` (CSPRNG); never `random`/uuid4 for the capability token; `storage_secret` from env, long random |
| V7/V14 Config & logging | yes | Secrets only in `.env` (gitignored) via `SecretStr`; do not log Realtime URL/keys; keep `realtime`/`websockets` loggers ≥ INFO |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Session id enumeration/guessing | Information Disclosure | 128-bit token, unique index, uniform 404 for unknown/malformed, rate-limit out of scope (local v1) |
| Public (publishable) key calls `create_session` or reads tables | Tampering / Info Disclosure | `REVOKE` + RLS deny-all (validated `permission denied` for anon/authenticated) |
| Stored XSS via project/display name | Tampering | Render with `ui.label` only; never `ui.html`/`ui.markdown` on user text |
| Secret key leakage (browser, repo, logs, WS URL) | Information Disclosure | Server-only; `.env` + `.gitignore`; `SecretStr`; log hygiene; secret keys also 401 from browsers [CITED: supabase.com/docs/guides/api/api-keys] |
| Spam session creation | DoS | Accepted for local v1; DB length checks bound row size |
| Cookie/storage forgery | Spoofing | Signed cookie; random `storage_secret`; name is non-authoritative |

## Project Constraints (from CLAUDE.md)

- Stack fixed: Python 3.12 (≥3.11), FastAPI, NiceGUI 3.18, supabase-py 2.33 async client, uvicorn single worker, pydantic/pydantic-settings, uv, ruff, pytest + pytest-asyncio (`asyncio_mode=auto`), NiceGUI `user` fixture.
- Realtime only via Supabase Realtime (no polling loops, no `ui.timer` DB re-query); async client only (`acreate_client`).
- Python is the single gateway; no Supabase keys in the browser; RLS enabled with no anon policies.
- NiceGUI: `@ui.page` functions only (no script mode); single worker; no global-scope UI.
- Closed-session immutability must be DB-enforced (Phase 4) — Phase 1 schema must not make that harder (columns present; deletes noted).
- Integer renumbering of `order_index` forbidden: schema uses `double precision`.
- Prefer new `sb_secret_` key; verify Realtime acceptance in Phase 1; legacy `service_role` JWT fallback.
- Workflow: all file changes must go through a GSD command (execute via `/gsd-execute-phase`).
- No project skills directories exist (`.claude/skills`, `.agents/skills` absent).

## Suggested Plan Slicing (for the planner; vertical MVP)

1. **Foundation + schema:** `uv` scaffold, `.gitignore`, settings, `.env.example`, `supabase init` + migration file, pytest config; checkpoint:human-verify (deps) → checkpoint:human-action (create `.env`, `supabase db push --linked`).
2. **Create → open → name:** tokens, repository (`create_session`, `get_session`), `SessionService`, `deps`, home page, canvas page (4 quadrants, not-found, name banner, `ensure_display_name`), UI + unit tests with fakes, integration tests for RPC.
3. **Realtime proof + docs:** `RealtimeHub` (+ fake-message unit tests), probe repo method, lifespan wiring, `/healthz`, `__main__` launcher, integration probe test, README (env vars, migrations, single worker, which Realtime key worked), human-verify of the two-browser flow.

## Sources

### Primary (HIGH confidence)
- Installed packages inspected this session (nicegui 3.18.0, supabase/realtime/postgrest 2.33.0, starlette 1.9.0, fastapi 0.160.0): `nicegui/ui_run_with.py`, `page.py`, `client.py`, `storage.py`, `nicegui.py`, `testing/*`; `realtime/_async/{client,channel}.py`, `realtime/{types,message}.py`; `postgrest/_async/request_builder.py`; `supabase/_async/client.py`; `starlette/middleware/sessions.py`
- Scratch prototypes (pages, storage, 404, dialog flow, factory/launcher, route order, lifespan) and a Postgres 17 container run of the migration — all executed 2026-10-22
- PyPI JSON API (`pypi.org/pypi/<pkg>/json`) — versions, python requirements, first-release dates
- https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically — dates, grant SQL
- https://supabase.com/docs/guides/api/hardening-data-api and /docs/guides/database/functions — grants, EXECUTE revocation, definer/invoker
- https://supabase.com/docs/guides/realtime/postgres-changes — publication SQL, replica identity, per-subscriber authorization, filters/limits
- https://supabase.com/docs/guides/api/api-keys — secret key → `service_role`/BYPASSRLS, keys are not JWTs, Realtime 24 h note
- Project docs: `.planning/{PROJECT,REQUIREMENTS,STATE,ROADMAP}.md`, `.planning/research/*`, `01-CONTEXT.md`, `.claude/CLAUDE.md`

### Secondary (MEDIUM confidence)
- https://github.com/orgs/supabase/discussions/29260 — 24 h connection limit with secret keys
- https://github.com/supabase/supabase-py/blob/main/src/realtime/README.md — `API_KEY` JWT statement, usage

### Tertiary (LOW confidence)
- Web searches for `sb_secret_` + Realtime returned no authoritative statement (basis for A1); `replication_ready` semantics unconfirmed (A4)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — resolved and imported together; versions from PyPI
- Architecture: HIGH — factory/route-order/lifespan/launcher/test harness all executed
- Schema/migration: HIGH for SQL semantics (executed on PG 17 with stub roles), MEDIUM for hosted-specific behavior (grants default, publication on hosted not executed)
- Realtime auth with `sb_secret_`: LOW-MEDIUM — unresolved until first live run (by design)
- Pitfalls: HIGH for items marked VERIFIED, MEDIUM otherwise

**Research date:** 2026-10-22
**Valid until:** 2026-11-05 (fast-moving: Supabase grant-default change lands 2026-10-30; FastAPI/NiceGUI release cadence)
