"""CARD-02 / CARD-08 live proofs of the ``cards_touch`` trigger and ``edit_card`` scoping.

Raw ``supabase_client`` writes stand in for any other writer: the database, not the app, owns
``updated_at`` (strictly increasing, never rewound) and ``text_updated_at`` (set only by a real
text change, never forged), so the Phase 2 stale guard and the "(edited)" marker are trustworthy.
"""

import secrets
from datetime import datetime

import pytest

from app.db.repository import Repository
from app.services.sessions import CardGone, SessionService
from app.tokens import new_session_id

pytestmark = pytest.mark.integration

LONG_AGO = "2000-01-01T00:00:00+00:00"


async def _new_session(client, created_session_ids: list[str]):
    repo = Repository(client)
    sid = new_session_id()
    await repo.create_session("IT edit storage " + secrets.token_hex(4), sid)
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


async def _insert_raw(client, workspace_id: str, quadrant_id: str, **overrides) -> dict:
    result = (
        await client.table("cards")
        .insert(_raw_card(workspace_id, quadrant_id, **overrides))
        .execute()
    )
    return result.data[0]


async def _update_raw(client, card_id: str, values: dict) -> dict:
    result = await client.table("cards").update(values).eq("id", card_id).execute()
    assert len(result.data) == 1
    return result.data[0]


def _ts(row: dict, column: str) -> datetime | None:
    value = row[column]
    return None if value is None else datetime.fromisoformat(value)


async def test_text_update_stamps_text_updated_at(supabase_client, created_session_ids):
    _, workspace_id, quadrants = await _new_session(supabase_client, created_session_ids)
    inserted = await _insert_raw(supabase_client, workspace_id, quadrants["IS"], text="before")
    assert inserted["text_updated_at"] is None

    updated = await _update_raw(supabase_client, inserted["id"], {"text": "after"})

    assert updated["text"] == "after"
    assert _ts(updated, "updated_at") > _ts(inserted, "updated_at")
    assert updated["text_updated_at"] is not None
    assert _ts(updated, "text_updated_at") == _ts(updated, "updated_at")
    assert updated["author"] == "Raw"
    assert updated["created_at"] == inserted["created_at"]


async def test_non_text_updates_keep_text_updated_at(supabase_client, created_session_ids):
    _, workspace_id, quadrants = await _new_session(supabase_client, created_session_ids)
    inserted = await _insert_raw(supabase_client, workspace_id, quadrants["IS"], text="steady")
    previous = inserted

    steps = [
        {"order_index": 2048.0},
        {"quadrant_id": quadrants["DOES"]},
        {"text": "steady"},  # identical text is not an edit
        {"deleted_at": "2026-10-23T00:00:00+00:00"},
    ]
    for values in steps:
        row = await _update_raw(supabase_client, inserted["id"], values)
        assert _ts(row, "updated_at") > _ts(previous, "updated_at"), values
        assert row["text_updated_at"] is None, values
        previous = row

    assert previous["text"] == "steady"
    assert previous["quadrant_id"] == quadrants["DOES"]


async def test_writer_cannot_rewind_or_forge_timestamps(supabase_client, created_session_ids):
    _, workspace_id, quadrants = await _new_session(supabase_client, created_session_ids)
    inserted = await _insert_raw(supabase_client, workspace_id, quadrants["IS"], text="steady")

    forged = await _update_raw(
        supabase_client,
        inserted["id"],
        {"updated_at": LONG_AGO, "text_updated_at": LONG_AGO},
    )
    assert _ts(forged, "updated_at") > _ts(inserted, "updated_at")
    assert forged["text_updated_at"] is None

    # Forging next to a real text change: the trigger's stamp wins on both columns.
    edited = await _update_raw(
        supabase_client,
        inserted["id"],
        {"text": "really edited", "updated_at": LONG_AGO, "text_updated_at": LONG_AGO},
    )
    assert _ts(edited, "updated_at") > _ts(forged, "updated_at")
    assert _ts(edited, "text_updated_at") == _ts(edited, "updated_at")
    assert _ts(edited, "text_updated_at") > datetime.fromisoformat(LONG_AGO)

    # A later non-text write cannot clear the marker either.
    cleared = await _update_raw(
        supabase_client, inserted["id"], {"text_updated_at": None, "order_index": 4096.0}
    )
    assert cleared["text_updated_at"] == edited["text_updated_at"]
    assert _ts(cleared, "updated_at") > _ts(edited, "updated_at")


async def test_edit_card_service_scoping(supabase_client, created_session_ids):
    repo, workspace_id, quadrants = await _new_session(supabase_client, created_session_ids)
    _, other_workspace_id, other_quadrants = await _new_session(
        supabase_client, created_session_ids
    )
    service = SessionService(repo)
    mine = await _insert_raw(supabase_client, workspace_id, quadrants["IS"], text="mine")
    gone = await _insert_raw(supabase_client, workspace_id, quadrants["IS"], text="gone")
    await _update_raw(supabase_client, gone["id"], {"deleted_at": "2026-10-23T00:00:00+00:00"})
    foreign = await _insert_raw(
        supabase_client, other_workspace_id, other_quadrants["IS"], text="foreign"
    )

    async def stored(card_id: str) -> dict:
        result = await supabase_client.table("cards").select("*").eq("id", card_id).execute()
        return result.data[0]

    gone_before = await stored(gone["id"])
    foreign_before = await stored(foreign["id"])

    with pytest.raises(CardGone):
        await service.edit_card(workspace_id, gone["id"], "revived")
    with pytest.raises(CardGone):
        await service.edit_card(workspace_id, foreign["id"], "hijacked")

    assert await stored(gone["id"]) == gone_before
    assert await stored(foreign["id"]) == foreign_before

    edited = await service.edit_card(workspace_id, mine["id"], "  Mine, edited  ")
    assert edited.text == "Mine, edited"
    assert edited.author == "Raw"
    assert edited.text_updated_at == edited.updated_at
    assert (await stored(mine["id"]))["text"] == "Mine, edited"
