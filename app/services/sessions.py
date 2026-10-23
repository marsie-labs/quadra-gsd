"""Session domain service. Pages call this; they never touch the repository or any key."""

import logging
from collections.abc import Sequence
from typing import Literal

from postgrest.exceptions import APIError

from app.db.repository import Repository
from app.models import CardView, QuadrantView, SessionView
from app.tokens import SESSION_ID_RE, new_session_id

logger = logging.getLogger(__name__)

MAX_PROJECT_NAME = 100
PROJECT_NAME_ERROR = "Required (max 100 characters)"

MAX_CARD_TEXT = 500
CARD_TEXT_ERROR = "Card text is required (max 500 characters)"
MAX_AUTHOR = 40

ORDER_GAP = 1024.0  # gapped double-precision ordering (ARCHITECTURE.md), never renumbered


def next_order_index(current_max: float | None) -> float:
    """The order_index that places a new card after every existing one in its quadrant."""
    if current_max is None:
        return ORDER_GAP
    return current_max + ORDER_GAP


def reorder_index(
    ordered: Sequence[tuple[str, float]], card_id: str, direction: Literal["up", "down"]
) -> float | None:
    """The order_index that moves ``card_id`` one place up or down, or None for "nothing to do".

    ``ordered`` is the quadrant's live cards in display order as (id, order_index) pairs. The card
    must land between the neighbour it passes and the next card beyond it with a strictly
    different order_index, so a card tied with others passes the whole tie group (ties sort by
    created_at and id, which this rule cannot change). At the top or bottom the new value is the
    neighbour's order_index minus or plus ORDER_GAP. Nothing is renumbered.

    None when the card is absent, already first (up) or last (down), or no double lies strictly
    between the two bounds (precision exhausted).
    """
    position = next((i for i, (other_id, _) in enumerate(ordered) if other_id == card_id), None)
    if position is None:
        return None
    step = -1 if direction == "up" else 1
    neighbour = position + step
    if not 0 <= neighbour < len(ordered):
        return None
    passed = ordered[neighbour][1]
    beyond = neighbour + step
    while 0 <= beyond < len(ordered) and ordered[beyond][1] == passed:
        beyond += step
    if not 0 <= beyond < len(ordered):
        return passed - ORDER_GAP if direction == "up" else passed + ORDER_GAP
    far = ordered[beyond][1]
    low, high = (far, passed) if direction == "up" else (passed, far)
    value = (low + high) / 2
    return value if low < value < high else None


class InvalidProjectName(ValueError):
    """The project name is empty after trimming or longer than MAX_PROJECT_NAME."""


def validate_project_name(raw: str | None) -> str | None:
    """Return the trimmed name, or None when invalid.

    Length counts Unicode code points (Python ``len``), matching Postgres ``char_length`` in the
    workspaces CHECK, so the UI, the service and the database agree.
    """
    if raw is None:
        return None
    name = raw.strip()
    if not 1 <= len(name) <= MAX_PROJECT_NAME:
        return None
    return name


class InvalidCardText(ValueError):
    """The card text is empty after trimming or longer than MAX_CARD_TEXT."""


class InvalidCardAuthor(ValueError):
    """The card author is empty after trimming or longer than MAX_AUTHOR."""


class CardGone(LookupError):
    """The card does not exist in this session or is already deleted."""


def validate_card_text(raw: str | None) -> str | None:
    """Return the trimmed card text, or None when invalid.

    Like ``validate_project_name``: trim first, then count Unicode code points (Python ``len``),
    which is what Postgres ``char_length`` counts on the stored trimmed text.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not 1 <= len(text) <= MAX_CARD_TEXT:
        return None
    return text


class SessionService:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    async def create_session(self, project_name: str) -> str:
        name = validate_project_name(project_name)
        if name is None:
            raise InvalidProjectName(PROJECT_NAME_ERROR)
        for attempt in (1, 2):
            session_id = new_session_id()
            try:
                await self._repository.create_session(name, session_id)
            except APIError as exc:
                # 23505 = unique_violation on session_id: astronomically unlikely, retry once.
                if exc.code == "23505" and attempt == 1:
                    logger.warning("session_id collision, retrying with a fresh token")
                    continue
                raise
            return session_id
        raise AssertionError("unreachable")  # pragma: no cover

    async def get(self, session_id: str) -> SessionView | None:
        # Malformed ids can never exist: answer "not found" without probing the database.
        if not SESSION_ID_RE.fullmatch(session_id):
            return None
        row = await self._repository.get_session(session_id)
        if row is None:
            return None
        quadrants = sorted(
            (QuadrantView(**q) for q in row["quadrants"]),
            key=lambda q: q.position,
        )
        return SessionView(
            session_id=row["session_id"],
            workspace_id=row["id"],
            project_name=row["project_name"],
            status=row["status"],
            quadrants=quadrants,
        )

    async def add_card(
        self, workspace_id: str, quadrant_id: str, text: str, author: str
    ) -> CardView:
        """Store a card at the end of its quadrant, after validating text and author.

        Both checks run before any repository call; the stored text and author are trimmed.
        """
        clean_text = validate_card_text(text)
        if clean_text is None:
            raise InvalidCardText(CARD_TEXT_ERROR)
        clean_author = author.strip()
        if not 1 <= len(clean_author) <= MAX_AUTHOR:
            raise InvalidCardAuthor("Author is required (max 40 characters)")
        current_max = await self._repository.max_order_index(quadrant_id)
        row = await self._repository.insert_card(
            workspace_id=workspace_id,
            quadrant_id=quadrant_id,
            text=clean_text,
            author=clean_author,
            order_index=next_order_index(current_max),
        )
        return CardView.model_validate(row)

    async def edit_card(self, workspace_id: str, card_id: str, text: str) -> CardView:
        """Change a card's text. Validates before any repository call; raises CardGone when the
        card is missing, deleted or in another session. No author: anyone may edit (D-05)."""
        clean_text = validate_card_text(text)
        if clean_text is None:
            raise InvalidCardText(CARD_TEXT_ERROR)
        row = await self._repository.update_card_text(
            workspace_id=workspace_id, card_id=card_id, text=clean_text
        )
        if row is None:
            raise CardGone(card_id)
        return CardView.model_validate(row)

    async def delete_card(self, workspace_id: str, card_id: str) -> CardView | None:
        """Soft-delete a card. Returns the deleted row, or None when the card was already deleted
        or is not in this session: deleting twice, or two participants at once, is not an error."""
        row = await self._repository.soft_delete_card(workspace_id=workspace_id, card_id=card_id)
        if row is None:
            return None
        return CardView.model_validate(row)

    async def move_card(self, workspace_id: str, card_id: str, quadrant_id: str) -> CardView:
        """Move a card to the end of ``quadrant_id`` (D-09), the way ``add_card`` places a new one.

        Raises CardGone when the card is missing, deleted or in another session; a quadrant of
        another session is refused by the database (APIError 23503). No author: anyone may move
        any card (D-05), and the card's author and text are untouched.
        """
        current_max = await self._repository.max_order_index(quadrant_id)
        row = await self._repository.move_card(
            workspace_id=workspace_id,
            card_id=card_id,
            quadrant_id=quadrant_id,
            order_index=next_order_index(current_max),
        )
        if row is None:
            raise CardGone(card_id)
        return CardView.model_validate(row)

    async def reorder_card(
        self, workspace_id: str, card_id: str, direction: Literal["up", "down"]
    ) -> CardView:
        """Move a card one place up or down in its quadrant by writing ONE row (CARD-05).

        The new position is computed from the database's current order of the quadrant, never
        from what a browser shows. Nothing is written when the card is already first (up) or last
        (down) there, or when no double fits between its new neighbours: the card is returned
        unchanged. The quadrant is never renumbered. Raises CardGone when the card is missing,
        deleted or in another session. No author: anyone may reorder any card (D-05).
        """
        if direction not in ("up", "down"):
            raise ValueError(f"unknown direction: {direction!r}")
        row = await self._repository.get_card(workspace_id=workspace_id, card_id=card_id)
        if row is None:
            raise CardGone(card_id)
        ordered = [
            (r["id"], float(r["order_index"]))
            for r in await self._repository.list_quadrant_order(row["quadrant_id"])
        ]
        value = reorder_index(ordered, card_id, direction)
        if value is None:
            return CardView.model_validate(row)
        moved = await self._repository.set_card_order(
            workspace_id=workspace_id, card_id=card_id, order_index=value
        )
        if moved is None:
            raise CardGone(card_id)
        return CardView.model_validate(moved)

    async def list_cards(self, workspace_id: str) -> list[CardView]:
        rows = await self._repository.list_cards(workspace_id)
        return [CardView.model_validate(r) for r in rows]
