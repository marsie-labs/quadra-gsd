"""D-02 groundwork: the database refuses an invalid card author, same 1-40 code-point rule.

IDEN-03 itself (recording the author on a card) belongs to Phase 2; this proves the CHECK that
Phase 2's card writes will rely on, before any card exists.
"""

import secrets

import pytest
from postgrest.exceptions import APIError

from app.db.repository import Repository
from app.tokens import new_session_id

pytestmark = pytest.mark.integration


async def _insert(client, workspace_id: str, quadrant_id: str, author: str):
    return (
        await client.table("cards")
        .insert(
            {
                "workspace_id": workspace_id,
                "quadrant_id": quadrant_id,
                "text": "x",
                "order_index": 1024.0,
                "author": author,
            }
        )
        .execute()
    )


async def test_db_enforces_author_length_like_validate_display_name(
    supabase_client, created_session_ids
):
    repo = Repository(supabase_client)
    sid = new_session_id()
    await repo.create_session("IT author " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)
    row = await repo.get_session(sid)
    assert row is not None
    workspace_id = row["id"]
    quadrant_id = row["quadrants"][0]["id"]

    try:
        with pytest.raises(APIError) as empty:
            await _insert(supabase_client, workspace_id, quadrant_id, "")
        assert empty.value.code == "23514"

        with pytest.raises(APIError) as too_long:
            await _insert(supabase_client, workspace_id, quadrant_id, "a" * 41)
        assert too_long.value.code == "23514"

        author = "é" * 40
        result = await _insert(supabase_client, workspace_id, quadrant_id, author)
        assert result.data[0]["author"] == author
    finally:
        await supabase_client.table("cards").delete().eq("workspace_id", workspace_id).execute()
