"""The only module that talks PostgREST. Uses the async Supabase client exclusively."""

from datetime import UTC, datetime
from typing import Any

from app.settings import Settings
from supabase import AsyncClient, acreate_client

CARD_COLUMNS = (
    "id, workspace_id, quadrant_id, text, order_index, author, created_at, updated_at, deleted_at"
)


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

    async def upsert_probe(self, nonce: str) -> None:
        """Write the realtime_probe row (id=1) carrying ``nonce``.

        The first call produces an INSERT event and later ones UPDATE events. The Realtime
        startup check waits for the event that carries the nonce.
        """
        await (
            self._client.table("realtime_probe")
            .upsert({"id": 1, "nonce": nonce, "pinged_at": datetime.now(UTC).isoformat()})
            .execute()
        )

    async def insert_card(
        self,
        *,
        workspace_id: str,
        quadrant_id: str,
        text: str,
        author: str,
        order_index: float,
    ) -> dict[str, Any]:
        """Insert one card; id, created_at and updated_at come from the database defaults."""
        resp = await (
            self._client.table("cards")
            .insert(
                {
                    "workspace_id": workspace_id,
                    "quadrant_id": quadrant_id,
                    "text": text,
                    "author": author,
                    "order_index": order_index,
                }
            )
            .execute()
        )
        return resp.data[0]

    async def max_order_index(self, quadrant_id: str) -> float | None:
        """Highest order_index among the quadrant's live cards, or None when it has none."""
        resp = await (
            self._client.table("cards")
            .select("order_index")
            .eq("quadrant_id", quadrant_id)
            .is_("deleted_at", "null")
            .order("order_index", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data
        if not rows:
            return None
        return float(rows[0]["order_index"])
