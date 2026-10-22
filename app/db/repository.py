"""The only module that talks PostgREST. Uses the async Supabase client exclusively."""

from typing import Any

from app.settings import Settings
from supabase import AsyncClient, acreate_client


async def connect(settings: Settings) -> AsyncClient:
    """Create the async Supabase client with the server-side secret key."""
    return await acreate_client(
        settings.supabase_url, settings.supabase_secret_key.get_secret_value()
    )


class Repository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create_session(self, project_name: str, session_id: str) -> str:
        """Create the workspace and its four quadrants in one transaction (RPC)."""
        resp = await self._client.rpc(
            "create_session",
            {"p_project_name": project_name, "p_session_id": session_id},
        ).execute()
        return resp.data

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return the workspace row with embedded quadrants, or None when it does not exist."""
        resp = await (
            self._client.table("workspaces")
            .select("id, session_id, project_name, status, quadrants(id, kind, position)")
            .eq("session_id", session_id)
            .maybe_single()
            .execute()
        )
        # maybe_single() returns None (not an empty response) when no row matches.
        if resp is None:
            return None
        return resp.data
