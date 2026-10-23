"""The /s/{session_id} page: four labeled quadrants, or a real 404 for an unknown link."""

from nicegui import ui

from app.deps import get_services
from app.ui.canvas_view import CanvasView
from app.ui.identity import current_name, name_banner


def register() -> None:
    @ui.page("/s/{session_id}", response_timeout=10)
    async def canvas(session_id: str) -> None:
        view = await get_services().sessions.get(session_id)
        if view is None:
            ui.context.client.status_code = 404
            ui.label("Session not found").classes("text-h5")
            ui.label("This link does not match any session.")
            ui.link("Create a new session", "/")
            return

        with ui.row().classes("items-center"):
            ui.label(view.project_name).classes("text-h5").mark("project-name")
            # Read-only text (D-03): no input and no rename control. Empty when unnamed.
            header_name = ui.label(current_name() or "").classes("text-grey").mark("display-name")

        def on_name_saved(name: str) -> None:
            header_name.text = name

        if current_name() is None:
            # Inline and ignorable, never a blocking modal (D-01).
            name_banner(on_saved=on_name_saved)

        canvas_view = CanvasView(view, on_name_saved=on_name_saved)
        canvas_view.build()
        hub = get_services().hub
        hub.register(canvas_view)
        # Closed tabs must leave the registry, or the hub keeps feeding dead views (Pitfall 4).
        ui.context.client.on_delete(lambda: hub.unregister(canvas_view))
