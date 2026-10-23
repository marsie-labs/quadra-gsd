"""View models shared by the service layer and the UI."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

QuadrantKind = Literal["IS", "IS_NOT", "DOES", "DOES_NOT"]

QUADRANT_LABELS: dict[str, str] = {
    "IS": "IS",
    "IS_NOT": "IS NOT",
    "DOES": "DOES",
    "DOES_NOT": "DOES NOT",
}


class QuadrantView(BaseModel):
    id: str
    kind: QuadrantKind
    position: int


class SessionView(BaseModel):
    session_id: str
    workspace_id: str  # internal workspaces.id; never rendered
    project_name: str
    status: Literal["open", "closed"]
    quadrants: list[QuadrantView]


class CardView(BaseModel):
    """A card row as stored in ``cards`` (also the shape of a Realtime ``record``)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    workspace_id: str
    quadrant_id: str
    text: str
    author: str
    order_index: float
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


def card_sort_key(card: CardView) -> tuple[float, datetime, str]:
    """Display order inside a quadrant: (order_index, created_at, id)."""
    return (card.order_index, card.created_at, card.id)
