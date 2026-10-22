"""The / page: a project-name form that creates a session and navigates to its link."""

import logging

from nicegui import ui

from app.deps import get_services
from app.services.sessions import PROJECT_NAME_ERROR, InvalidProjectName, validate_project_name

logger = logging.getLogger(__name__)


def register() -> None:
    @ui.page("/")
    async def home() -> None:
        async def create() -> None:
            if not name_input.validate():
                return
            create_button.disable()  # in-flight guard: a double-click must create one session
            try:
                session_id = await get_services().sessions.create_session(name_input.value or "")
            except InvalidProjectName:
                name_input.error = PROJECT_NAME_ERROR
                return
            except Exception as exc:
                logger.warning("create_session failed: %s", exc)
                ui.notify("Could not create the session. Please try again.", type="negative")
                return
            finally:
                create_button.enable()
            ui.navigate.to(f"/s/{session_id}")

        ui.label("Quadra").classes("text-h4")
        name_input = ui.input(
            "Project name",
            validation={PROJECT_NAME_ERROR: lambda v: validate_project_name(v) is not None},
        )
        name_input.on("keydown.enter", create)
        create_button = ui.button("Create", on_click=create)
