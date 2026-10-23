"""The /s/{session_id} page: four labeled quadrants, or a real 404 for an unknown link.

Page open is read-then-render: the session is read, the (still loading) canvas registers with the
hub, the cards are read, and only then is anything drawn. Realtime events that arrive during the
card read are buffered by the canvas and replayed after the snapshot. A database failure answers
503 "Temporarily unavailable"; it must never fall into the 404 branch, or a valid capability link
would be reported as unknown during a blip (Phase 1 review WR-05).
"""

import logging

from nicegui import ui

from app.deps import get_services
from app.ui.canvas_view import CanvasView
from app.ui.identity import current_name, name_banner

logger = logging.getLogger(__name__)


def _render_unavailable(exc: Exception) -> None:
    """The 503 page: fixed text only, the log carries just the exception class."""
    logger.warning("canvas load failed: %s", type(exc).__name__)
    ui.context.client.status_code = 503
    ui.label("Temporarily unavailable").classes("text-h5")
    ui.label("Could not load this session. Please reload in a moment.")


def register() -> None:
    @ui.page("/s/{session_id}", response_timeout=10)
    async def canvas(session_id: str) -> None:
        services = get_services()
        try:
            view = await services.sessions.get(session_id)
        except Exception as exc:
            _render_unavailable(exc)
            return
        if view is None:
            ui.context.client.status_code = 404
            ui.label("Session not found").classes("text-h5")
            ui.label("This link does not match any session.")
            ui.link("Create a new session", "/")
            return

        # Register BEFORE the card read: a card changed in between still arrives as an event,
        # which the loading canvas buffers and replays after the snapshot.
        canvas_view = CanvasView(view, on_name_saved=lambda name: on_name_saved(name))
        hub = services.hub
        hub.register(canvas_view)
        # Closed tabs must leave the registry, or the hub keeps feeding dead views (Pitfall 4).
        ui.context.client.on_delete(lambda: hub.unregister(canvas_view))
        try:
            cards = await services.sessions.list_cards(view.workspace_id)
        except Exception as exc:
            hub.unregister(canvas_view)
            _render_unavailable(exc)
            return

        with ui.row().classes("items-center"):
            ui.label(view.project_name).classes("text-h5").mark("project-name")
            # Read-only text (D-03): no input and no rename control. Empty when unnamed.
            header_name = ui.label(current_name() or "").classes("text-grey").mark("display-name")

        banner: ui.element | None = None

        def on_name_saved(name: str) -> None:
            header_name.text = name
            # Naming through the add dialog must also retire the stale inline banner.
            if banner is not None and not banner.is_deleted:
                banner.delete()

        if current_name() is None:
            # Inline and ignorable, never a blocking modal (D-01).
            banner = name_banner(on_saved=on_name_saved)

        canvas_view.build()
        canvas_view.load_snapshot(cards)

        # NiceGUI runs connect handlers on every socket handshake. The first one is the page's
        # own initial connect (the cards were just read); each later one is a reconnect to a
        # canvas that stayed alive on the server, and may have missed events.
        handshakes = 0

        def on_connect() -> None:
            nonlocal handshakes
            handshakes += 1
            if handshakes > 1:
                canvas_view.request_resync()

        ui.context.client.on_connect(on_connect)
