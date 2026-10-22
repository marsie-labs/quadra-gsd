"""In-memory stand-in for the Repository, so service and UI tests run without Supabase.

``install_fake_services`` wires the REAL ``SessionService`` over ``FakeRepository``, so the
validation, retry and pre-filter logic under test is production code; only PostgREST is faked.
"""

import uuid
from typing import Any

from postgrest.exceptions import APIError

import app.deps
from app.deps import Services
from app.services.sessions import SessionService
from app.tokens import SESSION_ID_RE

SEEDED_ID_A = "SeededSessionAaaaaaaaa"
SEEDED_ID_B = "SeededSessionBbbbbbbbb"
SEEDED_NAME_A = "Seeded Project A"
SEEDED_NAME_B = "Seeded Project B"

_KINDS = ("IS", "IS_NOT", "DOES", "DOES_NOT")


class FakeRepository:
    """Mimics ``Repository`` including the DB CHECK constraints and unique session_id."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.create_calls = 0
        self.get_calls = 0
        self.fail_next_create_codes: list[str] = []

    async def create_session(self, project_name: str, session_id: str) -> str:
        self.create_calls += 1
        if self.fail_next_create_codes:
            code = self.fail_next_create_codes.pop(0)
            raise APIError({"code": code, "message": "injected"})
        name = project_name.strip()
        if not SESSION_ID_RE.fullmatch(session_id) or not 1 <= len(name) <= 100:
            raise APIError({"code": "23514", "message": "check constraint violated"})
        if session_id in self.rows:
            raise APIError({"code": "23505", "message": "duplicate session_id"})
        self.rows[session_id] = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "project_name": name,
            "status": "open",
            "quadrants": [
                {"id": str(uuid.uuid4()), "kind": kind, "position": position}
                for position, kind in enumerate(_KINDS, start=1)
            ],
        }
        return session_id

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        self.get_calls += 1
        row = self.rows.get(session_id)
        if row is None:
            return None
        return {**row, "quadrants": [dict(q) for q in row["quadrants"]]}


def install_fake_services(seed: dict[str, str] | None = None) -> FakeRepository:
    """Seed ``{session_id: project_name}`` rows and install a real service over the fake."""
    repo = FakeRepository()
    for session_id, project_name in (seed or {}).items():
        repo.rows[session_id] = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "project_name": project_name,
            "status": "open",
            "quadrants": [
                {"id": str(uuid.uuid4()), "kind": kind, "position": position}
                for position, kind in enumerate(_KINDS, start=1)
            ],
        }
    app.deps.services = Services(sessions=SessionService(repo))  # type: ignore[arg-type]
    return repo
