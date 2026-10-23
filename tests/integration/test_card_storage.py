"""CARD-07 live proofs: stored card shape, gapped ordering, ties and the DB text boundaries."""

import secrets

import pytest
from postgrest.exceptions import APIError

from app.db.repository import Repository
from app.services.sessions import SessionService
from app.tokens import new_session_id

pytestmark = pytest.mark.integration


async def _new_session(client, created_session_ids: list[str]):
    repo = Repository(client)
    sid = new_session_id()
    await repo.create_session("IT storage " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)
    row = await repo.get_session(sid)
    assert row is not None
    quadrants = {q["kind"]: q["id"] for q in row["quadrants"]}
    return repo, row["id"], quadrants


def _raw_card(workspace_id: str, quadrant_id: str, **overrides):
    return {
        "workspace_id": workspace_id,
        "quadrant_id": quadrant_id,
        "text": "raw",
        "order_index": 1024.0,
        "author": "Raw",
    } | overrides


async def test_stored_card_has_every_column(supabase_client, created_session_ids):
    repo, workspace_id, quadrants = await _new_session(supabase_client, created_session_ids)
    service = SessionService(repo)

    card = await service.add_card(workspace_id, quadrants["IS"], "  Stored card  ", "Ann")

    result = await supabase_client.table("cards").select("*").eq("id", card.id).execute()
    assert len(result.data) == 1
    row = result.data[0]
    assert row["text"] == "Stored card"
    assert row["quadrant_id"] == quadrants["IS"]
    assert row["workspace_id"] == workspace_id
    assert row["author"] == "Ann"
    assert row["order_index"] == 1024.0
    assert row["created_at"] == row["updated_at"]
    assert row["deleted_at"] is None


async def test_order_index_gap_and_ties(supabase_client, created_session_ids):
    repo, workspace_id, quadrants = await _new_session(supabase_client, created_session_ids)
    service = SessionService(repo)
    is_id = quadrants["IS"]

    first = await service.add_card(workspace_id, is_id, "first", "Ann")
    second = await service.add_card(workspace_id, is_id, "second", "Ann")
    assert first.order_index == 1024.0
    assert second.order_index == 2048.0

    # A raw writer may tie an existing order_index: no unique constraint, both rows are stored.
    tie = (
        await supabase_client.table("cards")
        .insert(_raw_card(workspace_id, is_id, text="tie", order_index=2048.0))
        .execute()
    )
    tie_id = tie.data[0]["id"]

    gone = (
        await supabase_client.table("cards")
        .insert(_raw_card(workspace_id, is_id, text="gone", order_index=512.0))
        .execute()
    )
    await (
        supabase_client.table("cards")
        .update({"deleted_at": "2026-10-23T00:00:00+00:00"})
        .eq("id", gone.data[0]["id"])
        .execute()
    )

    cards = await service.list_cards(workspace_id)
    assert [c.text for c in cards] == ["first", "second", "tie"]
    assert [c.id for c in cards][2] == tie_id
    assert cards[1].created_at <= cards[2].created_at
    assert all(c.deleted_at is None for c in cards)


async def test_db_text_boundaries(supabase_client, created_session_ids):
    _, workspace_id, quadrants = await _new_session(supabase_client, created_session_ids)
    is_id = quadrants["IS"]

    ok = (
        await supabase_client.table("cards")
        .insert(_raw_card(workspace_id, is_id, text="é" * 500))
        .execute()
    )
    assert ok.data[0]["text"] == "é" * 500

    with pytest.raises(APIError) as too_long:
        await (
            supabase_client.table("cards")
            .insert(_raw_card(workspace_id, is_id, text="a" * 501))
            .execute()
        )
    assert too_long.value.code == "23514"

    with pytest.raises(APIError) as blank:
        await (
            supabase_client.table("cards")
            .insert(_raw_card(workspace_id, is_id, text="   "))
            .execute()
        )
    assert blank.value.code == "23514"
