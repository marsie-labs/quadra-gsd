# Quadra

Quadra is a realtime collaborative boundary canvas. A small team opens a shared session via a link and fills four quadrants (IS, IS NOT, DOES, DOES NOT) with cards. When the session is closed, an external agent pulls the structured result by `session_id`.

It is Python end to end: FastAPI and NiceGUI for the server and UI, Supabase PostgreSQL for persistence, and Supabase Realtime events relayed by the Python server.

This README covers Phases 1 to 3. Phase 1 is the session skeleton: create a session, open its unguessable link, enter a display name and see the four labeled quadrants, with the schema and the Realtime connection proven at startup. Phase 2 is the live shared canvas: add cards to any quadrant and watch every open browser update live, with the server recovering by itself from Realtime and connection loss. Phase 3 is card editing: edit, delete, move and reorder cards live.

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

The migrations, applied in order:

| Version | File | What it adds |
|---------|------|--------------|
| `20261022000000` | `supabase/migrations/20261022000000_init_schema.sql` | Sessions, quadrants, cards, the probe table, RLS and the Realtime publication. |
| `20261023000000` | `supabase/migrations/20261023000000_author_nonblank.sql` | Database checks that a card's author (and a closing name) is not blank and at most 40 characters. |
| `20261023120000` | `supabase/migrations/20261023120000_card_edit_tracking.sql` | Cards remember when their text was last edited (`text_updated_at`), and every card update gets a newer `updated_at` from a trigger. |

The app selects `text_updated_at`, so push migrations before starting a newer app version, or canvas pages answer "Temporarily unavailable".

Fallback when the CLI cannot reach the project: paste each migration file, in version order, into the Dashboard SQL editor and run it, then record each one as applied so the CLI stays in sync:

```bash
supabase migration repair --status applied 20261022000000 --linked
supabase migration repair --status applied 20261023000000 --linked
supabase migration repair --status applied 20261023120000 --linked
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
| `warn` | One ERROR is logged and the app starts anyway. The hub keeps recovering in the background. | `failed`, then `reconnecting`, then `verified` once Realtime is reachable |
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

`realtime.state` is one of `pending` (no check has run), `verified`, `failed`, `reconnecting` (the hub is recovering, see [Reconnects and restarts](#reconnects-and-restarts)) or `disabled`. `status` is `ok` when the state is `verified` or `disabled`, otherwise `degraded`.

## Realtime key

Outcome of the live run on this project (2026-10-22): hosted Supabase Realtime **accepts the `sb_secret_` key** (`SUPABASE_SECRET_KEY`). `SUPABASE_REALTIME_KEY` was not set and the legacy JWT was not needed. The probe event round trip took roughly 0.35 to 1.3 seconds across runs.

So `SUPABASE_REALTIME_KEY` is an optional override. Set it only if the startup check fails at stage `connect` with HTTP 401/403, for example on a project whose Realtime still requires a legacy JWT. A deliberately wrong key was also tried: it fails loudly at stage `connect` with HTTP 401, and the key text does not appear in the error or the console.

## Live cards

Each quadrant has an add field. The first time someone adds a card in a browser, the page asks for a display name; the name is stored in that browser and reused afterwards. Card text is 1 to 500 characters (it is trimmed first). A card shows "author · HH:MM", where the time is in the server's local time zone; hover it for the full timestamp.

## Editing cards

Click a card's text, or choose Edit in the card's ⋮ menu, to edit it in place. Enter saves, Shift+Enter starts a new line, clicking elsewhere saves and Esc cancels.

Edited cards show "(edited)" after the time.

The menu also has Move to (another quadrant; the card goes to the end), Move up and Move down (within the quadrant; each is disabled at its end) and Delete. Delete is immediate, with a "Card deleted" message; the card is kept in the database with `deleted_at`.

Anyone with the link can do all of this without entering a name, and the card keeps its original author.

Your own changes show at once. If saving fails, the card goes back and a message says so.

If someone changes a card you are editing, your text is kept, and the last save wins.

Reordering writes one row: the moved card gets an `order_index` between its new neighbours, so the other cards are never renumbered. If two people reorder one quadrant at the same time, every browser still shows the same order, also after a reload.

## Live updates

Every change reaches open browsers only through Supabase Realtime events relayed by the Python server. There is no polling and no timer-driven refresh: the server holds one Realtime subscription and fans each event out to the canvases of the session it belongs to.

Changes made outside the app appear live too. To see it, open a session in a browser, then run these statements in the Supabase Dashboard SQL editor (replace `<session_id>` with the id from the session link):

```sql
-- add a card to IS
insert into public.cards (workspace_id, quadrant_id, text, order_index, author)
select w.id, q.id, 'Hello from SQL', 1000000, 'SQL editor'
from public.workspaces w
join public.quadrants q on q.workspace_id = w.id and q.kind = 'IS'
where w.session_id = '<session_id>';

-- edit it
update public.cards set text = 'Edited in SQL' where text = 'Hello from SQL';

-- soft-delete it
update public.cards set deleted_at = now() where text = 'Edited in SQL';
```

The card appears, changes text and then disappears in every open browser without a reload.

A text change made in SQL also shows "(edited)" on the card.

With `REALTIME_CHECK=off` the server never connects to Realtime, so there are **no live updates at all**: a browser sees only what the database held when its page opened or reconnected. Use it for tests only.

## Reconnects and restarts

- **Browser reconnect.** When a browser loses its connection and comes back, its canvas reloads the cards from the database, so nothing written meanwhile is missed.
- **Server restart.** A restarted server reads the current cards from the database when a page opens; cards added while it was down are there.
- **Realtime recovery.** If the server's Realtime connection drops, the hub rebuilds it by itself. A channel error, a timeout, a re-join by the client library and a silently closed socket (for example the 24 hour limit on secret-key connections) are all handled. Attempts are spaced 1, 2, 4, 8, 16 and then 30 seconds apart until one works. The hub then proves again that database change events reach it (the same nonce probe as at startup), and only then asks every open canvas to reload its cards from the database, so no change can fall between the reload and the first live event. Cards are re-read only in response to such a loss, never on a timer.
- **Health.** While the hub recovers, `/healthz` reports realtime state `reconnecting` and status `degraded`; afterwards it reports `verified` again. A warn-mode startup failure no longer sticks: the hub keeps recovering and reports `verified` once Realtime is reachable.
- If the database itself cannot be read when a page opens, the page answers 503 "Temporarily unavailable" instead of "Session not found".

## Tests

```bash
uv run pytest -q                       # unit and UI tests, no network
uv run pytest -m integration -q -rs    # hosted Supabase; needs .env
uv run ruff check . && uv run ruff format --check .
```

The integration suite needs `.env` with `SUPABASE_URL`, `SUPABASE_SECRET_KEY` and `STORAGE_SECRET`, plus `SUPABASE_PUBLISHABLE_KEY` for the anonymous-denial test (without it that test is reported as skipped). It includes tests that start the real server as a subprocess, wait for `/healthz` to report `verified`, check the one-year session cookie and assert that no key appears in the console output (`test_realtime_probe.py`), restart the server and find a card written while it was down (`test_restart_recovery.py`), prove live fan-out and convergence (`test_live_cards.py`), and close the hub's Realtime socket and check that it recovers and the canvases pick up a card written during the outage (`test_realtime_recovery.py`), and prove the card actions live: edits and their storage (`test_live_card_edits.py`, `test_card_edit_storage.py`), move and delete (`test_card_actions_live.py`) and reordering with concurrent convergence (`test_card_reorder_live.py`).

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
  realtime/hub.py      Realtime hub: startup round-trip check, fan-out, recovery
  ui/                  NiceGUI pages: home, canvas page, canvas_view.py (live card projection), page registration
supabase/
  config.toml
  migrations/          SQL schema, pushed with the Supabase CLI
tests/
  unit/                settings, tokens, sessions service, hub (dispatch, recovery), launcher and /healthz
  ui/                  NiceGUI user-fixture tests
  integration/         hosted-Supabase tests (probe, live cards, restart and Realtime recovery)
```
