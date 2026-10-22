---
phase: 01-session-skeleton
reviewed: 2026-10-22T00:00:00Z
depth: standard
files_reviewed: 44
files_reviewed_list:
  - .env.example
  - .gitignore
  - README.md
  - app/__init__.py
  - app/__main__.py
  - app/db/__init__.py
  - app/db/repository.py
  - app/deps.py
  - app/main.py
  - app/models.py
  - app/realtime/__init__.py
  - app/realtime/hub.py
  - app/services/__init__.py
  - app/services/sessions.py
  - app/settings.py
  - app/tokens.py
  - app/ui/__init__.py
  - app/ui/canvas_page.py
  - app/ui/home_page.py
  - app/ui/identity.py
  - app/ui/pages.py
  - pyproject.toml
  - supabase/.gitignore
  - supabase/config.toml
  - supabase/migrations/20261022000000_init_schema.sql
  - tests/conftest.py
  - tests/integration/test_card_author_check.py
  - tests/integration/test_create_session.py
  - tests/integration/test_realtime_probe.py
  - tests/integration/test_rls_denies_anon.py
  - tests/integration/test_skeleton_e2e.py
  - tests/ui/fakes.py
  - tests/ui/test_canvas.py
  - tests/ui/test_ensure_name.py
  - tests/ui/test_home.py
  - tests/ui/test_identity.py
  - tests/ui/test_not_found.py
  - tests/ui/ui_main.py
  - tests/unit/test_app_factory.py
  - tests/unit/test_hub_dispatch.py
  - tests/unit/test_identity.py
  - tests/unit/test_sessions_service.py
  - tests/unit/test_settings.py
  - tests/unit/test_tokens.py
findings:
  critical: 0
  warning: 8
  info: 6
  total: 14
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-10-22
**Depth:** standard
**Files Reviewed:** 44
**Status:** issues_found

## Summary

The skeleton is small and mostly well structured: RLS is enabled with no anon policies and the grants are revoked from `anon`/`authenticated`, session ids are 128-bit CSPRNG tokens that are re-validated server-side, and the SQL RPC is atomic. No data-loss or authentication-bypass defects were found, so there are no BLOCKER-class issues.

The defects that matter are these:
- The secret-protection claims in `hub.py` and `settings.py` are not true in practice. Two were reproduced against the installed libraries.
- The home page create flow can create duplicate sessions.
- Start-up and page paths have no bounded failure handling.
- The `cards.author` CHECK is weaker than the rule the code and test docstrings say it enforces.

External leads (UI audit, security audit) were each re-checked against the source. The Enter re-entry claim, the missing error handling in the canvas page, the conditional logger pin, the missing `btrim` on `cards.author` and the missing probe write timeout are all confirmed. They appear below as WR-01, WR-05, WR-02, WR-07 and WR-04, tagged `(external: ...)`.

## Warnings

### WR-01: Home page can create duplicate sessions (Enter re-entry, re-enabled button) (external: ui-audit)

**File:** `app/ui/home_page.py:16-31, 38`
**Issue:** `create_button.disable()` guards only the button. `name_input.on("keydown.enter", create)` re-enters `create()` while the first call is still awaiting the RPC. Each re-entry passes validation and calls `create_session` again, producing a second workspace plus four quadrants (key repeat or a double Enter is enough). A second leak exists on the success path. The `finally: create_button.enable()` runs before `ui.navigate.to(...)`, so the button is clickable again between a successful create and the browser navigating away. The tests only assert `create_calls == 1` for a single Enter or click. Nothing covers a double trigger.
**Fix:** Use a re-entrancy flag that is independent of the button, and do not re-enable on success.
```python
creating = False

async def create() -> None:
    nonlocal creating
    if creating or not name_input.validate():
        return
    creating = True
    create_button.disable()
    try:
        session_id = await get_services().sessions.create_session(name_input.value or "")
    except InvalidProjectName:
        name_input.error = PROJECT_NAME_ERROR
    except Exception as exc:
        logger.warning("create_session failed: %s", exc)
        ui.notify("Could not create the session. Please try again.", type="negative")
    else:
        ui.navigate.to(f"/s/{session_id}")
        return  # stay locked while navigating
    creating = False
    create_button.enable()
```
Add a UI test that triggers `keydown.enter` twice against a slow fake repository and asserts `create_calls == 1`.

### WR-02: Realtime key-log protection is ineffective and an invalid URL leaks the key at ERROR level (external: security-audit R1/R2)

**File:** `app/realtime/hub.py:28-32`, `app/settings.py:18`
**Issue:** There are two related problems, both reproduced against the installed libraries.
1. The DEBUG pin is a no-op in the normal launch order. It runs at import time and only acts `if getEffectiveLevel() < INFO`. `app/__main__.py` imports `app.main` (and so `hub.py`) before `logging.basicConfig`. At import time the root logger is still at WARNING, so no level is set. Verified: after `import app.realtime.hub`, `logging.getLogger("realtime").level == 0`. Any later `basicConfig(level=DEBUG)` or `LOG_LEVEL=debug` then makes realtime-py print `Attempting to connect to WebSocket at wss://...?apikey=<secret key>`.
2. realtime-py logs `Connection attempt failed: {e}` at ERROR, outside the `_sanitize` path. `websockets` embeds the full URI in `InvalidURI`: `wss:///realtime/v1/websocket?apikey=SECRETKEY... isn't a valid URI: hostname isn't provided`. `Settings.supabase_url` is an unvalidated `str`, so an `https:///`-style typo reaches it and the service-level secret lands in the console. The module docstring says the key is "never logged".

The secret is the RLS-bypassing server key.
**Fix:** Validate the URL in settings (`AnyHttpUrl` with a non-empty host), and attach a redacting filter instead of a conditional level pin.
```python
class _RedactApiKey(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _APIKEY_RE.sub(r"\1***", str(record.getMessage()))
        record.args = ()
        return True

for _name in ("realtime", "websockets"):
    logging.getLogger(_name).addFilter(_RedactApiKey())
```
Loggers do not inherit filters to children, so attach the filter to the `realtime._async.client` logger (or the handler) as well. Add a test that logs an `apikey=` URL and asserts it is redacted.

### WR-03: A too-short `STORAGE_SECRET` is echoed verbatim in the startup traceback

**File:** `app/settings.py:30-38`
**Issue:** The `field_validator` raises `ValueError` after the value is parsed. Pydantic's `ValidationError` then prints `input_value='<the raw secret>'`. Reproduced with a 31-character secret: the whole value appears in the console, which is typically captured in service logs or a CI log. A 31-character secret is almost a valid one. This contradicts the module docstring's claim that secrets never show up in `repr`/`str`/logs.
**Fix:** Hide inputs in validation errors, and make the same choice for the other secret fields.
```python
model_config = SettingsConfigDict(
    env_file=".env", env_file_encoding="utf-8", extra="ignore",
    hide_input_in_errors=True,
)
```
Add a test asserting the raw value is absent from `str(ValidationError)`.

### WR-04: Startup check phases have no hard timeout (external: security-audit R5)

**File:** `app/realtime/hub.py:100, 147`
**Issue:** `timeout` bounds only the SUBSCRIBED wait and the event wait. `await self._rt.connect()` (up to 5 retries with doubling backoff) and `await write_probe(nonce)` run with no `asyncio.wait_for`. A stalled PostgREST write (the underlying httpx client has its own long default timeout) blocks the lifespan and therefore app startup, well beyond the documented ~15 seconds, with no stage named. In `verify_roundtrip`, the "bounded" re-write loop is only bounded between writes.
**Fix:** Wrap both calls.
```python
await asyncio.wait_for(write_probe(nonce), max(remaining_budget, 1.0))
```
Convert `TimeoutError` to `RealtimeCheckError("probe-write", ...)`. Wrap `connect()` the same way and report stage `connect`.

### WR-05: Canvas page has no handling for database failures (external: ui-audit)

**File:** `app/ui/canvas_page.py:13`
**Issue:** `await get_services().sessions.get(session_id)` is unguarded. Any `APIError`, `httpx` timeout, or a `KeyError` or `ValidationError` from a malformed row in `SessionService.get` produces NiceGUI's generic 500 page for a perfectly valid link. `response_timeout=10` also turns a slow query into a timeout error page. A transient Supabase blip is therefore indistinguishable from a broken link. The fix must not render the "Session not found" 404 branch on a DB error, because that would tell users a real link is invalid.
**Fix:**
```python
try:
    view = await get_services().sessions.get(session_id)
except Exception:
    logger.exception("session lookup failed")
    ui.context.client.status_code = 503
    ui.label("Temporarily unavailable").classes("text-h5")
    ui.label("Could not load this session. Please reload in a moment.")
    return
```

### WR-06: Banner and dialog handlers are not idempotent and can raise on a deleted element

**File:** `app/ui/identity.py:68, 104`
**Issue:**
- In `name_banner.submit`, `save_display_name` returns the stored name when one already exists, so a second Enter or Save (key repeat, double click, or another tab that already saved) reaches `banner.delete()` again. NiceGUI's `Element.remove` does `parent_slot.children.remove(element)`, which raises `ValueError` for an element that is already gone. The handler aborts and `on_saved` is skipped.
- In `ensure_display_name`, `dialog.delete()` after `await dialog` has the same problem. In NiceGUI 3.16 and later, awaiting a dialog resolves to `None` when it was deleted (for example on client disconnect), and the delete call then fails on an already-deleted element.

**Fix:**
```python
if not banner.is_deleted:
    banner.delete()
...
if not dialog.is_deleted:
    dialog.delete()
```

### WR-07: `cards.author` and `workspaces.closed_by` CHECKs accept whitespace-only values (external: security-audit R4)

**File:** `supabase/migrations/20261022000000_init_schema.sql:13, 34`
**Issue:** `cards.text` uses `char_length(btrim(text)) between 1 and 500` and `create_session` btrims the project name. `author` and `closed_by` only check `char_length(...)`, so `'   '` is a valid author at the database level. The Python rule (`validate_display_name`, which strips) rejects it. The test docstring says the database enforces the same 1-40 rule, but this is not true for blank names. The agent snapshot then contains cards with an invisible author, which breaks "never a placeholder author" (D-02) for any non-UI writer. The migration has probably already been pushed to the hosted project, so editing it in place would drift from the remote.
**Fix:** Add a forward migration, for example `20261022010000_author_btrim.sql`:
```sql
alter table public.cards
  add constraint cards_author_nonblank check (char_length(btrim(author)) between 1 and 40);
alter table public.workspaces
  add constraint workspaces_closed_by_nonblank
  check (closed_by is null or char_length(btrim(closed_by)) between 1 and 40);
```
Extend `test_card_author_check.py` with a `"   "` case that expects `23514`.

### WR-08: `integration_settings` turns any configuration error into a skip, so the integration suite can pass vacuously

**File:** `tests/conftest.py:19-25`
**Issue:** `except Exception: pytest.skip(...)` also swallows a real misconfiguration, such as a too-short `STORAGE_SECRET` or a malformed `SUPABASE_URL`. `pytest -m integration -q -rs` then reports every live test as skipped and exits 0 (the README's own verification command). Only a missing `.env` should skip.
**Fix:** Skip only when required variables are absent, and let validation errors fail.
```python
try:
    return Settings()
except ValidationError as exc:
    if all(e["type"] == "missing" for e in exc.errors()):
        pytest.skip("integration: .env with SUPABASE_URL, SUPABASE_SECRET_KEY, STORAGE_SECRET required")
    raise
```

## Info

### IN-01: `/healthz` returns raw exception text without authentication

**File:** `app/main.py:41`, `app/realtime/hub.py:186`
**Issue:** `error` is `type(exc).__name__: str(exc)` from the probe write or the connect step. That can include PostgREST messages (table or schema-cache details such as "Could not find the table 'public.realtime_probe'") and httpx errors. The README states that `/healthz` "exposes nothing else". The only scrubbing is the `apikey` regex.
**Fix:** Expose only `state`, `stage` and `latency_ms` on `/healthz`; keep the detail in the server log.

### IN-02: `SESSION_ID_RE` uses `$`, so `.match()` accepts a trailing newline

**File:** `app/tokens.py:7`, `tests/integration/test_skeleton_e2e.py:80`
**Issue:** The shared regex is anchored with `^...$`. Python's `$` also matches before a final `\n`. Every production use is `fullmatch`, which is safe, but the exported constant is a footgun and the e2e test already uses `.match`. Postgres `$` is strict, so the "mirrors the CHECK constraint" comment is slightly off.
**Fix:** `re.compile(r"[A-Za-z0-9_-]{22,64}")` and always use `fullmatch`, or anchor with `\A...\Z`.

### IN-03: In `warn` mode a failed check leaves the Realtime client running and the state can never recover

**File:** `app/realtime/hub.py:182-192`
**Issue:** On failure in warn mode the code does not call `stop()`, so the connection stays open and keeps auto-reconnecting. `state` stays `failed` for the life of the process even if the channel later joins, so `/healthz` reports `degraded` permanently. If this is intentional for Phase 2's resync, it deserves a comment.
**Fix:** Either stop the client in warn mode too, or document that Phase 2 must update the state on a later successful join.

### IN-04: Quadrants are sorted twice

**File:** `app/ui/canvas_page.py:33`, `app/services/sessions.py:63-66`
**Issue:** `SessionService.get` already returns quadrants ordered by `position`. The page sorts them again. This is redundant and creates two places that have to agree.
**Fix:** Drop the sort in the page, or drop it in the service and document the page as the owner.

### IN-05: A real hosted-project ref is committed in `.env.example` and the README

**File:** `.env.example:5`, `README.md:16`
**Issue:** `fligjsqzjoyedcuolwss` identifies the hosted project in a public template. The project URL is not a secret and access is protected by RLS plus revoked grants, but it hands anyone a target for the anon key and the Realtime endpoint.
**Fix:** Use `https://<project-ref>.supabase.co` as a placeholder in both files.

### IN-06: The e2e home-create test can leave rows behind in the hosted database

**File:** `tests/integration/test_skeleton_e2e.py:67-75`
**Issue:** `created_session_ids.append(sid)` runs only after `assert len(resp.data) == 1`. If that assertion fails, for example because WR-01 produced two sessions, the workspaces are never cleaned up from the shared Supabase project.
**Fix:** Register every returned `session_id` for cleanup before asserting.
```python
created_session_ids.extend(r["session_id"] for r in resp.data)
assert len(resp.data) == 1
```

---

_Reviewed: 2026-10-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
