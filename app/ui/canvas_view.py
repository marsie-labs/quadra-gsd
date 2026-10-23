"""CanvasView: the four quadrant columns of one open canvas and their live card widgets.

One instance per page visit. It is registered with the RealtimeHub (``CardListener``), which
calls ``apply_card`` for every card row of this workspace and ``remove_card`` for deletes and
moves to another session. ``apply_card`` is a keyed upsert, so the actor's own card (rendered
from the confirmed write and again from the Realtime echo) shows exactly once.
User text is rendered only through ``ui.label``: never HTML or Markdown.

Realtime replays nothing, so the view also keeps a snapshot protocol (SYNC-04). While a database
read is in flight (page open, resync) the view is *loading*: ``apply_card``/``remove_card`` calls
are buffered in arrival order. ``load_snapshot`` makes the view show exactly the snapshot, then
replays the buffer through the normal logic (its stale guard keeps newer rows), so a change newer
than the snapshot is neither lost nor undone. Cards are read on page open, on a reconnect
handshake and on ``request_resync()``; never on a timer.
"""

import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from nicegui import background_tasks, ui

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
        self._root: ui.element | None = None
        # Snapshot protocol. A new view is waiting for its first (page-open) snapshot, so it
        # starts with one read outstanding. Events that arrive meanwhile are buffered.
        self._reads_in_flight = 1
        self._pending: list[tuple[str, CardView | str]] = []
        # Resync single-flight: at most one read running and one rerun queued.
        self._resyncing = False
        self._rerun = False

    @property
    def loading(self) -> bool:
        return self._reads_in_flight > 0

    def build(self) -> None:
        with ui.grid().classes("grid-cols-1 md:grid-cols-2 gap-4 w-full") as self._root:
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
        """Project one full card row: upsert, move between quadrants, or drop when soft-deleted.

        Called for confirmed writes and Realtime events. A row older than the card shown (by
        ``updated_at``) is ignored; an equal or newer one wins, so direct DB edits that do not
        touch ``updated_at`` still apply. While a snapshot read is in flight the call is buffered.
        """
        if self.loading:
            self._pending.append(("apply", card))
            return
        self._apply(card)

    def _apply(self, card: CardView) -> None:
        if card.deleted_at is not None:
            self._remove(card.id)
            return
        container = self._lists.get(card.quadrant_id)
        if container is None:
            logger.warning("card for unknown quadrant skipped")
            return
        shown = self._cards.get(card.id)
        if shown is not None and card.updated_at < shown.updated_at:
            return
        self._remove(card.id)  # drops the old widget wherever it is (maybe another quadrant)
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

    def remove_card(self, card_id: str) -> None:
        """Drop a card's widget and state and refresh its quadrant's hint; unknown id: no-op."""
        if self.loading:
            self._pending.append(("remove", card_id))
            return
        self._remove(card_id)

    def _remove(self, card_id: str) -> None:
        card = self._cards.pop(card_id, None)
        widget = self._widgets.pop(card_id, None)
        if widget is not None:
            widget.delete()
        if card is not None:
            self._refresh_hint(card.quadrant_id)

    def begin_loading(self) -> None:
        """Start buffering card events until the matching ``load_snapshot`` (or failed resync)."""
        self._reads_in_flight += 1

    def load_snapshot(self, cards: list[CardView]) -> None:
        """Show exactly ``cards``, then (once no other read is outstanding) replay the buffer."""
        self._end_read(cards)

    def _end_read(self, cards: list[CardView] | None) -> None:
        """Finish one read: apply its snapshot if any, and go live when it was the last read."""
        self._reads_in_flight = max(0, self._reads_in_flight - 1)
        if cards is not None:
            self._replace_state(cards)
        if self.loading:
            return  # another read is still outstanding: keep buffering, replay after it
        pending, self._pending = self._pending, []
        for kind, argument in pending:
            if kind == "apply":
                self._apply(argument)  # type: ignore[arg-type]
            else:
                self._remove(argument)  # type: ignore[arg-type]

    def _replace_state(self, cards: list[CardView]) -> None:
        """Make the widgets and state equal the snapshot. Unchanged cards are left untouched."""
        wanted = {c.id for c in cards}
        for card_id in list(self._cards):
            if card_id not in wanted:
                self._remove(card_id)
        for card in sorted(cards, key=card_sort_key):
            if self._cards.get(card.id) == card:
                continue
            self._remove(card.id)  # the snapshot is authoritative: bypass the stale guard
            self._apply(card)

    async def resync(self) -> None:
        """Reload the cards from the database. Single-flight: concurrent calls coalesce.

        While a read runs, further calls only set a rerun flag, so at most one read is in flight
        and at most one more follows. A failed read keeps the cards shown and tells the user.
        """
        if self._resyncing:
            self._rerun = True
            return
        self._resyncing = True
        try:
            while True:
                self._rerun = False
                await self._resync_once()
                if not self._rerun:
                    return
        finally:
            self._resyncing = False

    async def _resync_once(self) -> None:
        self.begin_loading()
        try:
            cards = await get_services().sessions.list_cards(self.workspace_id)
        except Exception as exc:
            logger.warning("canvas resync failed: %s", type(exc).__name__)
            if not self._gone():
                self._end_read(None)  # keep what is shown, replay what arrived meanwhile
                self._notify("Could not refresh the cards. Reload the page to try again.")
            return
        if not self._gone():  # the tab may have closed during the read
            self._end_read(cards)

    def _gone(self) -> bool:
        return self._root is None or self._root.is_deleted

    def _notify(self, message: str) -> None:
        """``ui.notify`` needs a client context; a background resync runs outside any handler."""
        assert self._root is not None
        with self._root:
            ui.notify(message, type="warning")

    def request_resync(self) -> None:
        """Schedule ``resync()`` in the background. Plain def: callable from sync event code."""
        background_tasks.create(self.resync(), name=f"canvas resync {self.workspace_id}")

    def _refresh_hint(self, quadrant_id: str) -> None:
        has_cards = any(c.quadrant_id == quadrant_id for c in self._cards.values())
        self._empty[quadrant_id].set_visibility(not has_cards)
