"""Main file for the NiceGUI ``user`` fixture. Tests inject services; this never sets any."""

from nicegui import ui

from app.ui.identity import ensure_display_name
from app.ui.pages import register_pages

register_pages()


@ui.page("/_test/author-action")
def author_action() -> None:
    """TEST-ONLY page standing in for Phase 2's add-card handler (D-02 gate)."""
    result = ui.label("idle").mark("result")

    async def go() -> None:
        name = await ensure_display_name()
        result.text = "cancelled" if name is None else f"authored by {name}"

    ui.button("Add card", on_click=go)


ui.run(storage_secret="test-storage-secret-for-the-nicegui-user-fixture")
