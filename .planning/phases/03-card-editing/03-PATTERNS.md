# Phase 3: Card Editing - Pattern Map

**Mapped:** 2026-10-23
**Files analyzed:** 8 (no RESEARCH.md; derived from CONTEXT.md and code)
**Analogs found:** 7 / 8
All analogs are git-tracked (verified via `git ls-files` listing).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `supabase/migrations/2026102400000X_card_edit.sql` (new: `text_updated_at`, `updated_at` trigger) | migration | CRUD | `supabase/migrations/20261023000000_author_nonblank.sql` (+ init_schema DO block / `notify pgrst`) | role-match |
| `app/models.py` (CardView + `text_updated_at`) | model | transform | `CardView` itself, lines 32-45 | exact |
| `app/db/repository.py` (update_card_text, move_card, set_order_index, soft_delete_card) | repository | CRUD | `insert_card` / `max_order_index` (lines 59-98) | exact |
| `app/services/sessions.py` (edit_card, delete_card, move_card, reorder_card) | service | CRUD | `SessionService.add_card` (lines 110-131) | exact |
| `app/ui/canvas_view.py` (menu, inline editor, optimistic + rollback) | component | event-driven | `_build_quadrant`/`_add_card`/`_apply` (same file) | exact |
| `tests/ui/fakes.py` (FakeRepository update methods, gates, fail codes) | test helper | CRUD | `FakeRepository.insert_card` (lines 85-120) | exact |
| `tests/ui/test_card_editing.py` (new) | test | event-driven | `tests/ui/test_card_authoring.py` | exact |
| `tests/integration/test_card_edit.py` (new: trigger, soft delete, move FK) | test | CRUD | `tests/integration/test_card_storage.py` | exact |
| `tests/unit/test_sessions_service.py` (extend) | test | CRUD | itself | exact |

## Pattern Assignments

### `app/db/repository.py` (repository, CRUD)
**Analog:** `insert_card` / `max_order_index`. Only module touching PostgREST, async, returns raw dict rows.
```python
CARD_COLUMNS = (
    "id, workspace_id, quadrant_id, text, order_index, author, created_at, updated_at, deleted_at"
)  # line 9-11: append text_updated_at here

async def insert_card(self, *, workspace_id, quadrant_id, text, author, order_index) -> dict[str, Any]:
    resp = await (self._client.table("cards").insert({...}).execute())
    return resp.data[0]
```
New methods follow: `self._client.table("cards").update({...}).eq("id", card_id).is_("deleted_at","null").select?`.
Return `resp.data[0]` (full row, so the service builds `CardView`). Use `CARD_COLUMNS` for the select. Add a neighbor lookup like `max_order_index` (lines 84-98: `.eq("quadrant_id").is_("deleted_at","null").order("order_index")`) for reorder midpoint. Soft delete = update `{"deleted_at": now_iso}` (see `datetime.now(UTC).isoformat()` at line 55). An update that matches no row returns empty data: decide on raising.

### `app/services/sessions.py` (service, CRUD)
**Analog:** `add_card` (lines 110-131): validate first, before any repo call, then repo, then `CardView.model_validate(row)`.
```python
clean_text = validate_card_text(text)
if clean_text is None:
    raise InvalidCardText(CARD_TEXT_ERROR)
current_max = await self._repository.max_order_index(quadrant_id)
row = await self._repository.insert_card(..., order_index=next_order_index(current_max))
return CardView.model_validate(row)
```
Move-to-end (D-09) reuses `max_order_index` + `next_order_index` for the target quadrant. Reorder: midpoint of neighbors, or end +/- `ORDER_GAP` at edges; never renumber. No author/name needed (D-05). `ORDER_GAP`, `InvalidCardText` at lines 20, 48.

### `app/ui/canvas_view.py` (component, event-driven)
**Analog:** same file.

Marker + widget build (lines 150-156), the thing to extend with the editor, menu, and "(edited)" in the meta line:
```python
with container:
    with ui.card().classes("w-full").mark("card", f"card-{card.id}") as widget:
        ui.label(card.text).mark("card-text")
        ui.label(f"{card.author} · {format_card_time(card.created_at)}").classes(
            "text-caption text-grey").mark("card-meta").tooltip(format_card_timestamp(card.created_at))
```
Re-entrancy guard and inline-error pattern (lines 94-122): guard set before first await, released in `finally`; `field.error = CARD_TEXT_ERROR`; `field.on_value_change(lambda _, field=field: setattr(field, "error", None))`; `field.on("keydown.enter", add)`.
```python
if quadrant.id in self._adding:
    return
...
self._adding.add(quadrant.id)
try:
    try:
        card = await get_services().sessions.add_card(...)
    except InvalidCardText:
        field.error = CARD_TEXT_ERROR; return
    except Exception as exc:
        logger.warning("add_card failed: %s", type(exc).__name__)
        ui.notify("Could not add the card. Please try again.", type="negative")
        return
    self.apply_card(card)
finally:
    self._adding.discard(quadrant.id)
```
Add `self._editing: dict[str, ...]` (draft state) and per-card busy set mirroring `_adding`.

D-04 hook: `_apply` (lines 136-165) does `self._remove(card.id)` then rebuilds. Needed change: if card id is in editing state, update `self._cards[card.id]` (respecting the stale guard at lines 144-146) but do not delete/rebuild the widget; on cancel, re-render from the latest `self._cards`. If the card is deleted (`deleted_at`) mid-edit, `_remove` path at 137-139 closes the editor and notifies; a quadrant change is the planner's call. Note `_replace_state` (204-214) also removes and re-applies, and so needs the same exception.

Optimistic path: update `self._cards` and call `_apply` with a local `model_copy(update=...)`, then on failure `_apply` the previous card with a bypass of the stale guard (as `_replace_state` does at line 213: `_remove` first). The confirmed row (greater `updated_at`) and the echo then upsert by key with no duplicates. Rollback toast style: `ui.notify("Could not … Please try again.", type="negative")` in handler context (use `self._notify`-style `with self._root:` only outside handlers; note it currently uses type="warning").

Menu markers: give each item a distinct `.mark(...)`/accessible name (UI-REVIEW warning). Disabled up/down: `ui.menu_item(...).props("disable")`. Delete toast: `ui.notify("Card deleted")`. Labels for "Move to": `QUADRANT_LABELS` (imported line 24), skipping the current quadrant's kind.

### `app/models.py` (model)
`CardView` (lines 32-45): add `text_updated_at: datetime` (or default so older fake rows still validate). `extra="ignore"` is set, and `card_sort_key` (48-50) is unchanged. "(edited)" shown when `text_updated_at > created_at` (or nullable column non-null).

### Migration (forward-only; never edit the two pushed files)
**Analog style** (`20261023000000_author_nonblank.sql`): plain DDL statements, then `notify pgrst, 'reload schema';`. Naming `YYYYMMDDHHMMSS_name.sql`, later than 20261023000000. Contents: add column, `create function public.cards_touch() ... language plpgsql set search_path = ''` (init_schema functions use `security invoker`, `set search_path = ''`, lines 62-66), `before update` trigger bumping `updated_at = now()` always and `text_updated_at` only when `new.text is distinct from old.text`. `replica identity full` is already set (init_schema line 91), so UPDATE events carry the old quadrant. Phase 2 stale guard: older ignored, equal applies, so `updated_at` must strictly advance. Hosted `supabase db push` required.

### `tests/ui/fakes.py`
**Analog:** `FakeRepository.insert_card` (85-120): counter, optional `asyncio.Event` gate, `fail_next_*_codes` raising `APIError({"code": code, "message": "injected"})`, mirrors CHECKs (`len(text.strip(" "))`). Add `update_calls`, `update_gate`, `fail_next_update_codes`; fake updates must bump `updated_at` and `text_updated_at` as the trigger would. `seed_card` (170-190) needs the new column; `soft_delete_card` helper exists at line 200 for echo simulation.

### `tests/ui/test_card_editing.py`
**Analog:** `tests/ui/test_card_authoring.py`: `install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})`, `await user.open(PATH_A)`, `user.find(marker=...)`, `.type()`, `.click()`, `user.should_see(...)`, a failure-message constant (e.g. `FAILURE = "Could not add the card. Please try again."`), single browser per test (docstring note). Gates for double Enter, `fail_next_*_codes` for rollback. Also see `tests/ui/test_live_projection.py` for echo/stale simulation (not read).

### `tests/integration/test_card_edit.py`
**Analog:** `tests/integration/test_card_storage.py`: `pytestmark = pytest.mark.integration`, `_new_session(supabase_client, created_session_ids)` helper, `_raw_card` helper, `SessionService(repo)`. Prove: trigger bumps `updated_at`, `text_updated_at` unchanged on move/reorder, soft delete keeps the row, cross-workspace move rejected by composite FK (`APIError` code 23503).

## Shared Patterns

### Failure handling (all write handlers)
Source: `canvas_view.py` 111-117. Catch `InvalidCardText` for the inline error; catch `Exception`, `logger.warning("... failed: %s", type(exc).__name__)`, then `ui.notify("Could not …. Please try again.", type="negative")`. Phase 4 closed-session DB errors flow through the same path.

### Guard before first await, release in `finally`
Source: `canvas_view.py` 51, 95-100, 120-122. Apply to edit save, delete, move, and reorder per card id.

### User text only via `ui.label` / `ui.textarea` value; never HTML.
### Pages -> `get_services().sessions` -> `Repository`; UI never touches the client.

### Validation
Source: `sessions.py` 56-67 `validate_card_text`; UI pre-check `validate_card_text(field.value) is None` (canvas_view line 97) before the write; the service re-validates. Unchanged trimmed text: skip the write (D-03).

## No Analog Found

| File/Feature | Role | Reason |
|---|---|---|
| Inline textarea editor with Enter/Shift+Enter/blur/Esc | component | No existing edit-in-place widget; closest is the add `ui.input` (`keydown.enter`). Use `ui.textarea` with `.on("keydown.enter.prevent", ...)`, `.on("keydown.esc", ...)`, `.on("blur", ...)`; Shift+Enter falls through by only handling the non-shift event. Blur-after-Esc/Enter needs a "done" flag to avoid double save. |
| ⋮ `ui.menu` with submenu | component | No menus in the codebase yet. |
| DB `before update` trigger | migration | No triggers exist; only the `create_session` function style. |

## Metadata

**Analog search scope:** `app/`, `supabase/migrations/`, `tests/`
**Files read:** canvas_view.py, repository.py, sessions.py, models.py (CardView), fakes.py, both migrations/init_schema excerpts, test excerpts
**Pattern extraction date:** 2026-10-23
