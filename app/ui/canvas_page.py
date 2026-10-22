"""The /s/{session_id} page: four labeled quadrants, or a real 404 for an unknown link."""

from nicegui import ui

from app.deps import get_services
from app.models import QUADRANT_LABELS


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
        with ui.grid().classes("grid-cols-1 md:grid-cols-2 gap-4 w-full"):
            for q in sorted(view.quadrants, key=lambda q: q.position):
                with ui.card().mark(f"quadrant-{q.kind}"):
                    ui.label(QUADRANT_LABELS[q.kind]).classes("text-h6")
                    ui.label("No cards yet").classes("text-grey")
