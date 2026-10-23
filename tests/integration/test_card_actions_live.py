"""Live proof against hosted Supabase: card move and delete (CARD-03, CARD-04, CARD-08).

A move or a delete chosen in one browser's card menu shows in another within seconds; a deleted
card stays in the database with ``deleted_at``; two simultaneous deletes are harmless; and the
composite foreign key refuses a move into another session's quadrant.
"""

import asyncio
import secrets
import time
from datetime import datetime

import pytest
from postgrest.exceptions import APIError

import app.deps
from app.db.repository import Repository
from app.tokens import new_session_id

pytestmark = pytest.mark.integration


async def _new_session(client, created_session_ids: list[str], services):
    sid = new_session_id()
    await Repository(client).create_session("IT actions " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)
    session = await services.sessions.get(sid)
    assert session is not None
    return sid, session, {q.kind: q.id for q in session.quadrants}


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    (column,) = browser.find(marker=f"cards-{kind}").elements
    return [card.default_slot.children[0].text for card in column.default_slot.children]


async def _wait_for(predicate, retries: int = 100) -> None:
    """Read the test browser's elements until ``predicate()`` holds. The app itself has no loop
    or timer: only Realtime events move the other browser."""
    for _ in range(retries):
        if predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition not reached")


async def test_move_and_delete_show_live_and_keep_the_row(
    user, create_user, live_services, supabase_client, created_session_ids
):
    app.deps.services = live_services
    sid, session, quadrants = await _new_session(
        supabase_client, created_session_ids, live_services
    )
    token = secrets.token_hex(4)
    mover_text, anchor_text = f"Mover {token}", f"Anchor {token}"
    sessions = live_services.sessions
    mover = await sessions.add_card(session.workspace_id, quadrants["IS"], mover_text, "Ann")
    await sessions.add_card(session.workspace_id, quadrants["DOES"], anchor_text, "Ann")

    # The NiceGUI test plugin runs a handler under the most recently opened request's storage,
    # so the second browser opens first and the acting browser last.
    second = create_user()
    await second.open(f"/s/{sid}")
    await user.open(f"/s/{sid}")
    with second.scope(marker="cards-IS"):
        await second.should_see(mover_text, retries=50)

    # Move: Move to > DOES in the acting browser.
    started = time.monotonic()
    with user.scope(marker=f"card-{mover.id}"):
        user.find(marker="card-action-move-DOES").click()
    await _wait_for(lambda: _card_texts(user, "DOES") == [anchor_text, mover_text], retries=50)
    acting_ms = (time.monotonic() - started) * 1000  # at once, for the actor
    await _wait_for(lambda: _card_texts(second, "DOES") == [anchor_text, mover_text], retries=50)
    move_ms = (time.monotonic() - started) * 1000
    assert _card_texts(second, "IS") == []
    assert _card_texts(user, "IS") == []
    print(f"\nLIVE: move click -> actor sees it: {acting_ms:.0f} ms, browser B: {move_ms:.0f} ms")

    # Delete: the acting browser deletes the mover.
    started = time.monotonic()
    with user.scope(marker=f"card-{mover.id}"):
        user.find(marker="card-action-delete").click()
    await user.should_see("Card deleted")
    assert _card_texts(user, "DOES") == [anchor_text]  # at once, for the actor
    await _wait_for(lambda: _card_texts(second, "DOES") == [anchor_text], retries=100)
    delete_ms = (time.monotonic() - started) * 1000
    print(f"\nLIVE: delete click -> browser B no longer shows it: {delete_ms:.0f} ms")

    # CARD-03: the row is still there, soft-deleted, and nothing but its place changed.
    resp = await supabase_client.table("cards").select("*").eq("id", mover.id).execute()
    assert len(resp.data) == 1
    row = resp.data[0]
    assert row["deleted_at"] is not None
    assert row["quadrant_id"] == quadrants["DOES"]
    assert row["order_index"] == 2048.0
    assert row["text_updated_at"] is None  # D-05, D-06: moving and deleting never mark an edit
    assert row["author"] == "Ann"
    assert row["text"] == mover_text
    live = await sessions.list_cards(session.workspace_id)
    assert [c.text for c in live] == [anchor_text]


async def test_concurrent_deletes_are_idempotent(
    real_services, supabase_client, created_session_ids
):
    sessions = real_services.sessions
    _, session, quadrants = await _new_session(supabase_client, created_session_ids, real_services)
    card = await sessions.add_card(session.workspace_id, quadrants["IS"], "Doomed", "Ann")

    results = await asyncio.gather(
        sessions.delete_card(session.workspace_id, card.id),
        sessions.delete_card(session.workspace_id, card.id),
    )

    assert sum(result is not None for result in results) == 1  # the row is deleted once
    first = (
        await supabase_client.table("cards").select("deleted_at").eq("id", card.id).execute()
    ).data[0]["deleted_at"]
    assert first is not None
    assert await sessions.delete_card(session.workspace_id, card.id) is None
    again = (
        await supabase_client.table("cards").select("deleted_at").eq("id", card.id).execute()
    ).data[0]["deleted_at"]
    assert again == first
    assert datetime.fromisoformat(first)


async def test_move_into_another_sessions_quadrant_is_rejected(
    real_services, supabase_client, created_session_ids
):
    sessions = real_services.sessions
    _, first, first_quadrants = await _new_session(
        supabase_client, created_session_ids, real_services
    )
    _, second, second_quadrants = await _new_session(
        supabase_client, created_session_ids, real_services
    )
    card = await sessions.add_card(first.workspace_id, first_quadrants["IS"], "Stay", "Ann")
    before = (await supabase_client.table("cards").select("*").eq("id", card.id).execute()).data[0]

    with pytest.raises(APIError) as rejected:
        await sessions.move_card(first.workspace_id, card.id, second_quadrants["DOES"])

    assert rejected.value.code == "23503"
    after = (await supabase_client.table("cards").select("*").eq("id", card.id).execute()).data[0]
    assert after["quadrant_id"] == before["quadrant_id"] == first_quadrants["IS"]
    assert after["order_index"] == before["order_index"]
    assert after["updated_at"] == before["updated_at"]
    assert second.workspace_id != first.workspace_id
