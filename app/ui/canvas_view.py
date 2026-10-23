"""CanvasView: the four quadrant columns of one open canvas and their live card widgets.

One instance per page visit. It is registered with the RealtimeHub (``CardListener``), which
calls ``apply_card`` for every card row of this workspace and ``remove_card`` for deletes and
moves to another session. ``apply_card`` is a keyed upsert, so the actor's own card (rendered
from the confirmed write and again from the Realtime echo) shows exactly once.

Cards are projected in place: the view keeps the latest server row per card (``_cards``) and at
most one optimistic row per card while that card's write is in flight (``_optimistic``). What is
shown is the optimistic row if any, else the server row. ``_render`` creates a card's element once
and afterwards only updates its labels and position, so an echo never rebuilds the card or an
editor that is open inside it.
User text is rendered only through ``ui.label`` text or a textarea value: never HTML or Markdown.

Realtime replays nothing, so the view also keeps a snapshot protocol (SYNC-04). While a database
read is in flight (page open, resync) the view is *loading*: ``apply_card``/``remove_card`` calls
are buffered in arrival order. ``load_snapshot`` makes the view show exactly the snapshot, then
replays the buffer through the normal logic (its stale guard keeps newer rows), so a change newer
than the snapshot is neither lost nor undone. Cards are read on page open, on a reconnect
handshake and on ``request_resync()``; never on a timer.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from nicegui import background_tasks, ui

from app.deps import get_services
from app.models import QUADRANT_LABELS, CardView, QuadrantView, SessionView, card_sort_key
from app.services.sessions import CARD_TEXT_ERROR, CardGone, InvalidCardText, validate_card_text
from app.ui.identity import ensure_display_name

logger = logging.getLogger(__name__)

EDIT_FAILED = "Could not save the card. Please try again."
CARD_GONE = "This card was deleted."


def format_card_time(moment: datetime, tz: tzinfo | None = None) -> str:
    """``HH:MM`` in ``tz``; with None, in the server process's local zone (A-02)."""
    return moment.astimezone(tz).strftime("%H:%M")


def format_card_timestamp(moment: datetime, tz: tzinfo | None = None) -> str:
    """Full timestamp with zone name, used as the card's tooltip."""
    return moment.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


def card_meta_text(card: CardView, tz: tzinfo | None = None) -> str:
    """``Ann · 15:05``, plus `` (edited)`` once the card's text has changed (D-06)."""
    meta = f"{card.author} · {format_card_time(card.created_at, tz)}"
    if card.text_updated_at is not None:
        meta += " (edited)"
    return meta


@dataclass(slots=True)
class _CardWidgets:
    """The elements of one shown card. A bundle exists exactly while the card is shown."""

    card: ui.card
    text: ui.label
    meta: ui.label
    row: ui.row
    quadrant_id: str


@dataclass(slots=True)
class _EditSession:
    """An open inline editor: its textarea and the text it was opened with."""

    editor: ui.textarea
    original: str


class CanvasView:
    def __init__(self, session: SessionView, on_name_saved: Callable[[str], None]) -> None:
        self.workspace_id = session.workspace_id
        self._session = session
        self._on_name_saved = on_name_saved
        self._cards: dict[str, CardView] = {}
        self._widgets: dict[str, _CardWidgets] = {}
        # Optimistic overlay: at most one unconfirmed row per card, while its write is in flight.
        self._optimistic: dict[str, CardView] = {}
        # Cards with a write in flight: set before the first await, released in ``finally``.
        self._busy: set[str] = set()
        self._editing: dict[str, _EditSession] = {}
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
        if card.quadrant_id not in self._lists:
            logger.warning("card for unknown quadrant skipped")
            return
        shown = self._cards.get(card.id)
        if shown is not None and card.updated_at < shown.updated_at:
            return
        self._cards[card.id] = card
        self._render(card.id)

    def remove_card(self, card_id: str) -> None:
        """Drop a card's widget and state and refresh its quadrant's hint; unknown id: no-op."""
        if self.loading:
            self._pending.append(("remove", card_id))
            return
        self._remove(card_id)

    def _remove(self, card_id: str) -> None:
        self._cards.pop(card_id, None)
        self._optimistic.pop(card_id, None)
        self._editing.pop(card_id, None)
        self._render(card_id)

    def _shown(self, card_id: str) -> CardView | None:
        """The row the page should show: the optimistic row if any, else the server row."""
        row = self._optimistic.get(card_id) or self._cards.get(card_id)
        if row is None or row.deleted_at is not None:
            return None
        return row

    def _build_card(self, row: CardView, container: ui.element) -> _CardWidgets:
        card_id = row.id
        with container:
            with ui.card().classes("w-full").mark("card", f"card-{card_id}") as card:
                # The text label must stay the card's first child.
                text = (
                    ui.label(row.text)
                    .classes("whitespace-pre-wrap break-words cursor-pointer")
                    .mark("card-text")
                )
                text.on("click", lambda _, card_id=card_id: self._start_edit(card_id))
                with ui.row().classes("items-center justify-between w-full no-wrap") as meta_row:
                    meta = (
                        ui.label(card_meta_text(row))
                        .classes("text-caption text-grey-8")
                        .mark("card-meta")
                        .tooltip(format_card_timestamp(row.created_at))
                    )
        return _CardWidgets(
            card=card, text=text, meta=meta, row=meta_row, quadrant_id=row.quadrant_id
        )

    def _render(self, card_id: str) -> None:
        """Make the page match ``_shown(card_id)``: create, update in place, reposition or drop."""
        shown = self._shown(card_id)
        widgets = self._widgets.get(card_id)
        if shown is None:
            self._editing.pop(card_id, None)
            if widgets is not None:
                del self._widgets[card_id]
                widgets.card.delete()
                self._refresh_hint(widgets.quadrant_id)
            return
        container = self._lists.get(shown.quadrant_id)
        if container is None:
            logger.warning("card for unknown quadrant skipped")
            return
        if widgets is None:
            widgets = self._build_card(shown, container)
            self._widgets[card_id] = widgets
        else:
            if widgets.text.text != shown.text:
                widgets.text.text = shown.text
            meta = card_meta_text(shown)
            if widgets.meta.text != meta:
                widgets.meta.text = meta

        ordered = sorted(
            (
                row
                for other_id in self._widgets
                if (row := self._shown(other_id)) is not None
                and row.quadrant_id == shown.quadrant_id
            ),
            key=card_sort_key,
        )
        index = next(i for i, row in enumerate(ordered) if row.id == card_id)
        siblings = list(container.default_slot.children)
        if index >= len(siblings) or siblings[index] is not widgets.card:
            widgets.card.move(target_container=container, target_index=index)
        old_quadrant_id = widgets.quadrant_id
        widgets.quadrant_id = shown.quadrant_id
        self._refresh_hint(old_quadrant_id)
        self._refresh_hint(shown.quadrant_id)

    async def _write(
        self,
        card_id: str,
        optimistic: CardView | None,
        call: Callable[[], Awaitable[CardView]],
        failure: str,
        operation: str,
    ) -> None:
        """The one guarded write path: show ``optimistic`` at once, confirm or roll back.

        A second write for the same card while one is in flight is dropped. On failure the page
        falls back to the latest server row (remote changes received meanwhile included) and the
        participant is told. On success the confirmed row replaces the optimistic one, unless the
        card was removed meanwhile (the removal stands) or a newer remote row arrived (the stale
        guard keeps it and ``_render`` shows it).
        """
        if card_id in self._busy:
            return
        self._busy.add(card_id)
        try:
            if optimistic is not None:
                self._optimistic[card_id] = optimistic
            self._render(card_id)
            try:
                row = await call()
            except CardGone:
                # Deleted meanwhile (here or elsewhere): the removal stands, the card never returns.
                self._remove(card_id)
                self._notify(CARD_GONE)
                return
            except Exception as exc:
                logger.warning("%s failed: %s", operation, type(exc).__name__)
                self._optimistic.pop(card_id, None)
                self._render(card_id)
                ui.notify(failure, type="negative")
                return
            self._optimistic.pop(card_id, None)
            if card_id in self._cards:
                self._apply(row)
                if self.loading:
                    # A snapshot that started before this write must not undo it.
                    self._pending.append(("apply", row))
            self._render(card_id)
        finally:
            self._busy.discard(card_id)

    def _start_edit(self, card_id: str) -> None:
        """Swap the card's text for a textarea holding it (D-01). Enter saves (D-03)."""
        shown = self._shown(card_id)
        widgets = self._widgets.get(card_id)
        if shown is None or widgets is None or card_id in self._busy or card_id in self._editing:
            return
        with widgets.card:
            editor = (
                ui.textarea("Edit card", value=shown.text)
                .props("autogrow autofocus outlined dense")
                .classes("w-full")
                .mark("card-editor")
            )
        editor.move(target_index=1)  # right after the text label
        widgets.text.set_visibility(False)
        editor.on_value_change(lambda _, editor=editor: setattr(editor, "error", None))
        # Plain Enter saves; Shift+Enter keeps its default newline.
        editor.on(
            "keydown.enter.exact.prevent", lambda _, card_id=card_id: self._commit_edit(card_id)
        )
        self._editing[card_id] = _EditSession(editor=editor, original=shown.text)

    def _close_editor(self, card_id: str) -> None:
        session = self._editing.pop(card_id, None)
        if session is None:
            return
        session.editor.delete()
        widgets = self._widgets.get(card_id)
        if widgets is not None:
            widgets.text.set_visibility(True)

    async def _commit_edit(self, card_id: str) -> None:
        session = self._editing.get(card_id)
        shown = self._shown(card_id)
        if session is None or shown is None:
            return
        clean = validate_card_text(session.editor.value)
        if clean is None:
            session.editor.error = CARD_TEXT_ERROR  # the editor stays open (D-01)
            return
        self._close_editor(card_id)  # before any await
        optimistic = shown.model_copy(update={"text": clean, "text_updated_at": datetime.now(UTC)})
        await self._write(
            card_id,
            optimistic,
            lambda: get_services().sessions.edit_card(self.workspace_id, card_id, clean),
            EDIT_FAILED,
            "edit_card",
        )

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
            if card.deleted_at is not None:
                self._remove(card.id)
                continue
            if card.quadrant_id not in self._lists:
                logger.warning("card for unknown quadrant skipped")
                continue
            self._cards[card.id] = card  # the snapshot is authoritative: bypass the stale guard
            self._render(card.id)

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

    def _notify(self, message: str, type: str = "warning") -> None:
        """``ui.notify`` needs a client context; a background resync runs outside any handler."""
        assert self._root is not None
        with self._root:
            ui.notify(message, type=type)

    def request_resync(self) -> None:
        """Schedule ``resync()`` in the background. Plain def: callable from sync event code."""
        background_tasks.create(self.resync(), name=f"canvas resync {self.workspace_id}")

    def _refresh_hint(self, quadrant_id: str) -> None:
        has_cards = any(w.quadrant_id == quadrant_id for w in self._widgets.values())
        self._empty[quadrant_id].set_visibility(not has_cards)
