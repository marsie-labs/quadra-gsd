"""Live proof against hosted Supabase: card reordering (CARD-05, SC-4, CARD-08).

A Move up chosen in one browser shows in another and after a reload; a reorder writes exactly one
row (never a renumber); two participants reordering in one quadrant at the same time end on the
same order everywhere; and two writers updating one card at once end on the newest ``updated_at``.
"""

import asyncio
import secrets
from datetime import datetime

import pytest

import app.deps
from app.db.repository import Repository
from app.models import CardView, card_sort_key
from app.tokens import new_session_id

pytestmark = pytest.mark.integration


class RecordingListener:
    """A CardListener that keeps the newest row per card and queues every event on arrival."""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self.queue: asyncio.Queue[CardView] = asyncio.Queue()
        self.cards: dict[str, CardView] = {}

    def apply_card(self, card: CardView) -> None:
        shown = self.cards.get(card.id)
        if shown is None or card.updated_at >= shown.updated_at:
            self.cards[card.id] = card
        self.queue.put_nowait(card)

    def remove_card(self, card_id: str) -> None:
        self.cards.pop(card_id, None)


async def _new_session(client, created_session_ids: list[str], services):
    sid = new_session_id()
    await Repository(client).create_session("IT reorder " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)
    session = await services.sessions.get(sid)
    assert session is not None
    return sid, session, {q.kind: q.id for q in session.quadrants}


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    (column,) = browser.find(marker=f"cards-{kind}").elements
    return [card.default_slot.children[0].text for card in column.default_slot.children]


async def _wait_for(predicate, retries: int = 50) -> None:
    """Read the test browser's elements until ``predicate()`` holds (at most retries x 0.1 s).
    A test-harness wait: the app itself has no loop or timer, only Realtime events move the
    other browser."""
    for _ in range(retries):
        if predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition not reached")


async def test_reorder_shows_live_and_survives_reload(
    user, create_user, live_services, supabase_client, created_session_ids
):
    app.deps.services = live_services
    sid, session, quadrants = await _new_session(
        supabase_client, created_session_ids, live_services
    )
    token = secrets.token_hex(4)
    first, second_text, third = f"first {token}", f"second {token}", f"third {token}"
    sessions = live_services.sessions
    await sessions.add_card(session.workspace_id, quadrants["IS"], first, "Ann")
    await sessions.add_card(session.workspace_id, quadrants["IS"], second_text, "Ann")
    third_card = await sessions.add_card(session.workspace_id, quadrants["IS"], third, "Ann")

    # The NiceGUI test plugin runs a handler under the most recently opened request's storage,
    # so the second browser opens first and the acting browser last.
    other = create_user()
    await other.open(f"/s/{sid}")
    await user.open(f"/s/{sid}")
    await _wait_for(lambda: _card_texts(other, "IS") == [first, second_text, third])

    with user.scope(marker=f"card-{third_card.id}"):
        user.find(marker="card-action-up").click()

    expected = [first, third, second_text]
    await _wait_for(lambda: _card_texts(user, "IS") == expected)
    await _wait_for(lambda: _card_texts(other, "IS") == expected)

    # A browser that opens afterwards, and the database, show the same order.
    reloaded = create_user()
    await reloaded.open(f"/s/{sid}")
    await _wait_for(lambda: _card_texts(reloaded, "IS") == expected)
    stored = await sessions.list_cards(session.workspace_id)
    assert [c.text for c in stored if c.quadrant_id == quadrants["IS"]] == expected


async def test_reorder_writes_exactly_one_row(real_services, supabase_client, created_session_ids):
    sessions = real_services.sessions
    _, session, quadrants = await _new_session(supabase_client, created_session_ids, real_services)
    cards = [
        await sessions.add_card(session.workspace_id, quadrants["IS"], f"card {i}", "Ann")
        for i in range(3)
    ]

    async def read_rows() -> dict[str, dict]:
        resp = await (
            supabase_client.table("cards")
            .select("id, order_index, updated_at, text_updated_at")
            .eq("quadrant_id", quadrants["IS"])
            .execute()
        )
        return {row["id"]: row for row in resp.data}

    before = await read_rows()
    moved = await sessions.reorder_card(session.workspace_id, cards[2].id, "up")
    after = await read_rows()

    midpoint = (before[cards[0].id]["order_index"] + before[cards[1].id]["order_index"]) / 2
    assert moved.order_index == midpoint
    assert after[cards[2].id]["order_index"] == midpoint
    assert after[cards[2].id]["updated_at"] != before[cards[2].id]["updated_at"]
    assert after[cards[2].id]["text_updated_at"] is None
    for other in cards[:2]:  # no other row changed: the quadrant was not renumbered
        assert after[other.id] == before[other.id]


async def test_concurrent_reorders_converge(live_services, supabase_client, created_session_ids):
    sessions = live_services.sessions
    _, session, quadrants = await _new_session(supabase_client, created_session_ids, live_services)
    hub = live_services.hub
    listeners = [RecordingListener(session.workspace_id) for _ in range(2)]
    for listener in listeners:
        hub.register(listener)
    try:
        cards = [
            await sessions.add_card(session.workspace_id, quadrants["IS"], f"card {i}", "Ann")
            for i in range(4)
        ]

        fourth_up, first_down = await asyncio.gather(
            sessions.reorder_card(session.workspace_id, cards[3].id, "up"),
            sessions.reorder_card(session.workspace_id, cards[0].id, "down"),
        )
        wanted = {cards[3].id: fourth_up.updated_at, cards[0].id: first_down.updated_at}

        for listener in listeners:  # wait for both UPDATE events, event-driven
            while any(
                (shown := listener.cards.get(card_id)) is None or shown.updated_at < moved_at
                for card_id, moved_at in wanted.items()
            ):
                await asyncio.wait_for(listener.queue.get(), 5.0)
    finally:
        for listener in listeners:
            hub.unregister(listener)

    stored = await sessions.list_cards(session.workspace_id)
    expected = [c.id for c in stored if c.quadrant_id == quadrants["IS"]]
    print(f"\nLIVE: converged order after concurrent reorders: {[c.text for c in stored]}")
    for listener in listeners:
        shown = sorted(
            (c for c in listener.cards.values() if c.quadrant_id == quadrants["IS"]),
            key=card_sort_key,
        )
        assert [c.id for c in shown] == expected


async def test_racing_updates_of_one_card_end_on_the_newest_stamp(
    real_services, supabase_client, created_session_ids
):
    """Backstop truth: two writers hit one card at once. The test cannot force the two updates
    to overlap inside the database, so it proves the outcome either way: the stored row is the
    one with the greater updated_at (cards_touch never lets the stamp go backwards)."""
    sessions = real_services.sessions
    _, session, quadrants = await _new_session(supabase_client, created_session_ids, real_services)
    card = await sessions.add_card(session.workspace_id, quadrants["IS"], "race start", "Ann")

    first, second = await asyncio.gather(
        sessions.edit_card(session.workspace_id, card.id, "race A"),
        sessions.edit_card(session.workspace_id, card.id, "race B"),
    )

    print(f"\nLIVE: race A updated_at={first.updated_at.isoformat()}")
    print(f"LIVE: race B updated_at={second.updated_at.isoformat()}")
    assert first.updated_at != second.updated_at
    newest = max((first, second), key=lambda c: c.updated_at)
    row = (await supabase_client.table("cards").select("*").eq("id", card.id).execute()).data[0]
    assert row["text"] == newest.text
    assert datetime.fromisoformat(row["updated_at"]) == newest.updated_at
