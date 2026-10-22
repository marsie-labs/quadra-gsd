"""The / page: a project-name form that creates a session and navigates to its link."""

import logging

from nicegui import ui

from app.deps import get_services

logger = logging.getLogger(__name__)


def register() -> None:
    @ui.page("/")
    async def home() -> None:
        async def create() -> None:
            try:
                session_id = await get_services().sessions.create_session(name_input.value or "")
            except Exception as exc:
                logger.warning("create_session failed: %s", exc)
                ui.notify("Could not create the session. Please try again.", type="negative")
                return
            ui.navigate.to(f"/s/{session_id}")

        ui.label("Quadra").classes("text-h4")
        name_input = ui.input("Project name")
        ui.button("Create", on_click=create)
