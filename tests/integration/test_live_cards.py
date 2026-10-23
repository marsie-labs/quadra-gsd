"""Live proofs against hosted Supabase Realtime.

Tracer: a card added in one browser appears live in another. SYNC-03: changes written by a
client that bypasses the app (stand-in for the SQL editor) appear live. QUAL-02 / SYNC-01: two
registered clients converge on the same cards in the same order, and the latency is measured.
"""

import asyncio
import secrets
import statistics
import time
from datetime import UTC, datetime

import pytest

import app.deps
from app.db.repository import Repository, connect
from app.models import CardView, card_sort_key
from app.tokens import new_session_id


@pytest.mark.integration
async def test_card_added_in_one_browser_appears_live_in_another(
    user, create_user, live_services, supabase_client, created_session_ids
):
    app.deps.services = live_services
    sid = new_session_id()
    await Repository(supabase_client).create_session("IT live " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)

    # The NiceGUI test plugin runs a click handler under the most recently opened request's
    # storage, so the unnamed second browser opens first and the acting browser last.
    second = create_user()
    await second.open(f"/s/{sid}")  # stays unnamed

    await user.open(f"/s/{sid}")
    user.find(marker="name-input").clear().type("Ann")
    user.find("Save").click()
    await user.should_see(marker="display-name", content="Ann")

    text = "Live card " + secrets.token_hex(4)
    user.find(marker="add-input-DOES").type(text)
    started = time.monotonic()
    user.find(marker="add-button-DOES").click()
    with user.scope(marker="cards-DOES"):  # the card, not the typed input value
        await user.should_see(text, retries=50)

    with second.scope(marker="quadrant-DOES"):
        await second.should_see(text, retries=50)  # 5 s
        await second.should_see("Ann")
    elapsed = time.monotonic() - started
    print(f"\nLIVE: add click -> browser B sees card: {elapsed * 1000:.0f} ms")

    resp = await (
        supabase_client.table("cards")
        .select("id, workspace_id, quadrant_id, author, created_at")
        .eq("text", text)
        .execute()
    )
    assert len(resp.data) == 1
    row = resp.data[0]
    print(f"LIVE: raw created_at from DB read: {row['created_at']!r}")
    assert row["author"] == "Ann"

    session = await live_services.sessions.get(sid)
    assert session is not None
    doing = next(q for q in session.quadrants if q.kind == "DOES")
    assert row["quadrant_id"] == doing.id
    assert row["workspace_id"] == session.workspace_id


class RecordingListener:
    """A CardListener that timestamps every card event on arrival (event-driven, no polling)."""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self.queue: asyncio.Queue[tuple[float, CardView]] = asyncio.Queue()
        self.cards: dict[str, CardView] = {}

    def apply_card(self, card: CardView) -> None:
        self.cards[card.id] = card
        self.queue.put_nowait((time.monotonic(), card))

    def remove_card(self, card_id: str) -> None:
        self.cards.pop(card_id, None)


@pytest.mark.integration
async def test_outside_writer_changes_appear_live(
    user, live_services, supabase_client, integration_settings, created_session_ids
):
    """SYNC-03: insert, text edit, soft delete and hard delete from outside the app show live."""
    app.deps.services = live_services
    sid = new_session_id()
    await Repository(supabase_client).create_session("IT outside " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)
    session = await live_services.sessions.get(sid)
    assert session is not None
    quadrant = next(q for q in session.quadrants if q.kind == "IS")

    await user.open(f"/s/{sid}")

    outside = await connect(integration_settings)  # never touches Repository or SessionService
    try:
        token = secrets.token_hex(4)
        text, new_text = f"Outside insert {token}", f"Outside edit {token}"
        resp = (
            await outside.table("cards")
            .insert(
                {
                    "workspace_id": session.workspace_id,
                    "quadrant_id": quadrant.id,
                    "text": text,
                    "order_index": 4096.0,
                    "author": "Outside",
                }
            )
            .execute()
        )
        row_id = resp.data[0]["id"]
        await user.should_see(text, retries=50)

        await outside.table("cards").update({"text": new_text}).eq("id", row_id).execute()
        await user.should_see(new_text, retries=50)
        await user.should_not_see(text)

        stamp = datetime.now(UTC).isoformat()
        await outside.table("cards").update({"deleted_at": stamp}).eq("id", row_id).execute()
        await user.should_not_see(new_text, retries=100)

        other_text = f"Outside second {token}"
        resp = (
            await outside.table("cards")
            .insert(
                {
                    "workspace_id": session.workspace_id,
                    "quadrant_id": quadrant.id,
                    "text": other_text,
                    "order_index": 8192.0,
                    "author": "Outside",
                }
            )
            .execute()
        )
        other_id = resp.data[0]["id"]
        await user.should_see(other_text, retries=50)
        await outside.table("cards").delete().eq("id", other_id).execute()
        await user.should_not_see(other_text, retries=100)
    finally:
        await outside.postgrest.aclose()


@pytest.mark.integration
async def test_two_clients_converge_with_latency(
    live_services, supabase_client, created_session_ids
):
    """QUAL-02 / SYNC-01: two clients of one session converge; per-card latency is measured."""
    repo = Repository(supabase_client)
    sid_w, sid_w2 = new_session_id(), new_session_id()
    for sid in (sid_w, sid_w2):
        await repo.create_session("IT converge " + secrets.token_hex(4), sid)
        created_session_ids.append(sid)
    session_w = await live_services.sessions.get(sid_w)
    session_w2 = await live_services.sessions.get(sid_w2)
    assert session_w is not None and session_w2 is not None
    kinds = {q.kind: q.id for q in session_w.quadrants}

    client_a = RecordingListener(session_w.workspace_id)
    client_b = RecordingListener(session_w.workspace_id)
    foreign = RecordingListener(session_w2.workspace_id)
    hub = live_services.hub
    for listener in (client_a, client_b, foreign):
        hub.register(listener)

    latencies: list[float] = []
    try:
        for i in range(5):
            quadrant_id = kinds["IS" if i % 2 == 0 else "DOES"]
            t0 = time.monotonic()
            card = await live_services.sessions.add_card(
                session_w.workspace_id, quadrant_id, f"Card {i} {secrets.token_hex(3)}", "Ann"
            )
            arrived_a, seen_a = await asyncio.wait_for(client_a.queue.get(), 5.0)
            arrived_b, seen_b = await asyncio.wait_for(client_b.queue.get(), 5.0)
            assert seen_a.id == seen_b.id == card.id
            latencies.append(arrived_b - t0)
    finally:
        for listener in (client_a, client_b, foreign):
            hub.unregister(listener)

    # Report before asserting, so a failing run still shows the numbers.
    print(f"latencies_ms={[round(x * 1000) for x in latencies]}")
    print(f"over_1s_ms={[round(x * 1000) for x in latencies if x > 1.0]}")

    ms = [round(x * 1000) for x in latencies]
    assert max(latencies) <= 2.0, f"a card took longer than 2.0 s: latencies_ms={ms}"
    assert statistics.median(latencies) <= 1.0, f"median latency above 1.0 s: latencies_ms={ms}"

    stored = await live_services.sessions.list_cards(session_w.workspace_id)
    assert set(client_a.cards) == set(client_b.cards) == {c.id for c in stored}
    for quadrant_id in kinds.values():
        expected = [c.id for c in stored if c.quadrant_id == quadrant_id]
        for client in (client_a, client_b):
            shown = sorted(
                (c for c in client.cards.values() if c.quadrant_id == quadrant_id),
                key=card_sort_key,
            )
            assert [c.id for c in shown] == expected
    assert foreign.queue.empty()
