"""Participant display name: validation, per-browser memory and the inline name banner.

The name lives in NiceGUI's signed per-browser storage (``app.storage.user``), so it survives
reloads and carries across sessions. It is fixed once stored (D-03): ``save_display_name`` never
overwrites an existing name, so a stale banner in a second tab cannot rename the browser.

Canvas callers pass ``on_saved`` so the header updates. Phase 2's add-card handler must
``await ensure_display_name(on_saved=...)`` and abort when it returns None - there is never a
placeholder author (D-02).
"""

from collections.abc import Callable, MutableMapping
from typing import Any

from nicegui import app, ui

MAX_DISPLAY_NAME = 40
NAME_ERROR = "Name is required (max 40 characters)"
STORAGE_KEY = "display_name"


def validate_display_name(raw: str | None) -> str | None:
    """Return the trimmed name when it is 1-40 code points (matches cards.author CHECK)."""
    if raw is None:
        return None
    name = raw.strip()
    if 1 <= len(name) <= MAX_DISPLAY_NAME:
        return name
    return None


def _storage(storage: MutableMapping[str, Any] | None) -> MutableMapping[str, Any]:
    return app.storage.user if storage is None else storage


def current_name(storage: MutableMapping[str, Any] | None = None) -> str | None:
    """The stored display name, or None when absent or invalid."""
    value = _storage(storage).get(STORAGE_KEY)
    return validate_display_name(value) if isinstance(value, str) else None


def save_display_name(
    raw: str | None, storage: MutableMapping[str, Any] | None = None
) -> str | None:
    """Store a valid name once per browser; return the name now in effect, or None if invalid."""
    store = _storage(storage)
    existing = current_name(store)
    if existing is not None:
        return existing
    name = validate_display_name(raw)
    if name is None:
        return None
    store[STORAGE_KEY] = name
    return name


def name_banner(on_saved: Callable[[str], None]) -> ui.element:
    """Inline, non-modal prompt for a display name; removes itself once a name is saved."""
    with ui.card().classes("w-full").mark("name-banner") as banner:
        ui.label("Pick a display name so teammates know who added what.")
        field = ui.input("Your name").mark("name-input")

        def submit() -> None:
            name = save_display_name(field.value)
            if name is None:
                field.error = NAME_ERROR
                return
            if not banner.is_deleted:  # a second queued submit must not delete it again (WR-06)
                banner.delete()
            on_saved(name)

        field.on("keydown.enter", submit)
        ui.button("Save", on_click=submit)
    return banner


async def ensure_display_name(on_saved: Callable[[str], None] | None = None) -> str | None:
    """Authoring gate (D-02): the stored name, or a name collected via a dialog, or None.

    Returns the stored name immediately with no dialog. Otherwise opens a name dialog and returns
    the saved name once valid, or None on Cancel - the caller must then abort its action. It never
    returns or invents a placeholder.
    """
    existing = current_name()
    if existing is not None:
        return existing

    with ui.dialog() as dialog, ui.card():
        ui.label("Enter your name to continue")
        field = ui.input("Your name")

        def submit() -> None:
            name = save_display_name(field.value)
            if name is None:
                field.error = NAME_ERROR
                return
            dialog.submit(name)

        field.on("keydown.enter", submit)
        with ui.row():
            ui.button("Cancel", on_click=lambda: dialog.submit(None))
            ui.button("Continue", on_click=submit)

    result = await dialog
    if not dialog.is_deleted:
        dialog.delete()
    if result and on_saved is not None:
        on_saved(result)
    return result or None
