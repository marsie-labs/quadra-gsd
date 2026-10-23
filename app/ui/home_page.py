"""The / page: a project-name form that creates a session and navigates to its link."""

import logging

from nicegui import ui

from app.deps import get_services
from app.services.sessions import PROJECT_NAME_ERROR, InvalidProjectName, validate_project_name

logger = logging.getLogger(__name__)


def register() -> None:
    @ui.page("/")
    async def home() -> None:
        creating = False  # per page instance (one browser tab); never shared across browsers

        async def create() -> None:
            nonlocal creating
            if creating or not name_input.validate():
                return
            creating = True  # set before the first await so a second Enter/click returns early
            create_button.disable()
            try:
                session_id = await get_services().sessions.create_session(name_input.value or "")
            except InvalidProjectName:
                name_input.error = PROJECT_NAME_ERROR
            except Exception as exc:
                logger.warning("create_session failed: %s", exc)
                ui.notify("Could not create the session. Please try again.", type="negative")
            else:
                # Success: stay locked until the browser leaves the page.
                ui.navigate.to(f"/s/{session_id}")
                return
            # Every non-success outcome falls through to here so the user can retry.
            creating = False
            create_button.enable()

        ui.label("Quadra").classes("text-h4")
        name_input = ui.input(
            "Project name",
            validation={PROJECT_NAME_ERROR: lambda v: validate_project_name(v) is not None},
        )
        name_input.on("keydown.enter", create)
        create_button = ui.button("Create", on_click=create)
