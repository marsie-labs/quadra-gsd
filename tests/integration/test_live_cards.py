"""Tracer proof: a card added in one browser appears live in another through hosted Realtime."""

import secrets
import time

import pytest

import app.deps
from app.db.repository import Repository
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
