"""Session domain service. Pages call this; they never touch the repository or any key."""

from app.db.repository import Repository
from app.models import QuadrantView, SessionView
from app.tokens import new_session_id


class SessionService:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    async def create_session(self, project_name: str) -> str:
        session_id = new_session_id()
        await self._repository.create_session(project_name.strip(), session_id)
        return session_id

    async def get(self, session_id: str) -> SessionView | None:
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
