"""Session domain service. Pages call this; they never touch the repository or any key."""

import logging

from postgrest.exceptions import APIError

from app.db.repository import Repository
from app.models import QuadrantView, SessionView
from app.tokens import SESSION_ID_RE, new_session_id

logger = logging.getLogger(__name__)

MAX_PROJECT_NAME = 100
PROJECT_NAME_ERROR = "Required (max 100 characters)"


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
            project_name=row["project_name"],
            status=row["status"],
            quadrants=quadrants,
        )
