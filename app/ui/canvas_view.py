"""CanvasView: the four quadrant columns of one open canvas and their live card widgets.

One instance per page visit. It is registered with the RealtimeHub (``CardListener``), which
calls ``apply_card`` for every card row of this workspace. ``apply_card`` is a keyed upsert, so
the actor's own card (rendered from the confirmed write and again from the Realtime echo) shows
exactly once. User text is rendered only through ``ui.label``: never HTML or Markdown.
"""

import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from nicegui import ui

from app.deps import get_services
from app.models import QUADRANT_LABELS, CardView, QuadrantView, SessionView, card_sort_key
from app.services.sessions import CARD_TEXT_ERROR, InvalidCardText, validate_card_text
from app.ui.identity import ensure_display_name

logger = logging.getLogger(__name__)


def format_card_time(moment: datetime, tz: tzinfo | None = None) -> str:
    """``HH:MM`` in ``tz``; with None, in the server process's local zone (A-02)."""
    return moment.astimezone(tz).strftime("%H:%M")


def format_card_timestamp(moment: datetime, tz: tzinfo | None = None) -> str:
    """Full timestamp with zone name, used as the card's tooltip."""
    return moment.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


class CanvasView:
    def __init__(self, session: SessionView, on_name_saved: Callable[[str], None]) -> None:
        self.workspace_id = session.workspace_id
        self._session = session
        self._on_name_saved = on_name_saved
        self._cards: dict[str, CardView] = {}
        self._widgets: dict[str, ui.element] = {}
        self._lists: dict[str, ui.element] = {}
        self._empty: dict[str, ui.label] = {}
        # Quadrants with an add in flight: set before the first await, released in ``finally``.
        self._adding: set[str] = set()

    def build(self) -> None:
        with ui.grid().classes("grid-cols-1 md:grid-cols-2 gap-4 w-full"):
            # Render in the order the service returns (already sorted by position).
            for quadrant in self._session.quadrants:
                self._build_quadrant(quadrant)

    def _build_quadrant(self, quadrant: QuadrantView) -> None:
        with ui.card().mark(f"quadrant-{quadrant.kind}"):
            ui.label(QUADRANT_LABELS[quadrant.kind]).classes("text-h6")
            self._lists[quadrant.id] = (
                ui.column().classes("w-full gap-2").mark(f"cards-{quadrant.kind}")
            )
            self._empty[quadrant.id] = (
                ui.label("No cards yet").classes("text-grey").mark(f"empty-{quadrant.kind}")
            )
            with ui.row().classes("items-center w-full"):
                # No browser-side length limit or counter: it counts UTF-16 units and would block
                # valid 500-code-point emoji text. validate_card_text is the authority.
                field = ui.input("New card").mark(f"add-input-{quadrant.kind}")
                field.on_value_change(lambda _, field=field: setattr(field, "error", None))

                button = ui.button("Add").mark(f"add-button-{quadrant.kind}")

                async def add(_=None, quadrant=quadrant, field=field, button=button) -> None:
                    await self._add_card(quadrant, field, button)

                field.on("keydown.enter", add)
                button.on_click(add)

    async def _add_card(self, quadrant: QuadrantView, field: ui.input, button: ui.button) -> None:
        if quadrant.id in self._adding:
            return  # a write for this quadrant is already in flight (double click / double Enter)
        if validate_card_text(field.value) is None:
            field.error = CARD_TEXT_ERROR
            return
        self._adding.add(quadrant.id)
        button.disable()
        try:
            # Phase 1 D-02: no placeholder author ever. Cancel keeps the typed text.
            author = await ensure_display_name(on_saved=self._on_name_saved)
            if author is None:
                return
            try:
                card = await get_services().sessions.add_card(
                    self.workspace_id, quadrant.id, field.value or "", author
                )
            except InvalidCardText:
                field.error = CARD_TEXT_ERROR
                return
            except Exception as exc:
                logger.warning("add_card failed: %s", type(exc).__name__)
                ui.notify("Could not add the card. Please try again.", type="negative")
                return
            field.value = ""
            self.apply_card(card)
        finally:
            self._adding.discard(quadrant.id)
            button.enable()

    def apply_card(self, card: CardView) -> None:
        """Keyed upsert of one card widget; called for confirmed writes and Realtime events."""
        container = self._lists.get(card.quadrant_id)
        if container is None:
            logger.warning("card for unknown quadrant skipped")
            return
        old = self._widgets.pop(card.id, None)
        if old is not None:
            old_card = self._cards.get(card.id)
            old.delete()
            if old_card is not None and old_card.quadrant_id != card.quadrant_id:
                self._refresh_hint(old_card.quadrant_id)
        self._cards[card.id] = card

        with container:
            with ui.card().classes("w-full").mark("card", f"card-{card.id}") as widget:
                ui.label(card.text).mark("card-text")
                ui.label(f"{card.author} · {format_card_time(card.created_at)}").classes(
                    "text-caption text-grey"
                ).mark("card-meta").tooltip(format_card_timestamp(card.created_at))
        self._widgets[card.id] = widget

        ordered = sorted(
            (c for c in self._cards.values() if c.quadrant_id == card.quadrant_id),
            key=card_sort_key,
        )
        target = ordered.index(card)
        if target != len(ordered) - 1:
            widget.move(target_index=target)
        self._refresh_hint(card.quadrant_id)

    def _refresh_hint(self, quadrant_id: str) -> None:
        has_cards = any(c.quadrant_id == quadrant_id for c in self._cards.values())
        self._empty[quadrant_id].set_visibility(not has_cards)
