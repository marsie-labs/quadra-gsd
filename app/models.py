"""View models shared by the service layer and the UI."""

from typing import Literal

from pydantic import BaseModel

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
    project_name: str
    status: Literal["open", "closed"]
    quadrants: list[QuadrantView]
