"""Live proof against hosted Supabase: a card edited in one browser shows live in another.

Tracer for Phase 3 (CARD-02, CARD-08): click the card text, edit it inline, press Enter. The
row is written by ``SessionService.edit_card``, the ``cards_touch`` trigger stamps ``updated_at``
and ``text_updated_at``, and the Realtime echo updates the card in place in both browsers.
"""

import secrets
import time
from datetime import datetime

import pytest

import app.deps
from app.db.repository import Repository
from app.tokens import new_session_id


@pytest.mark.integration
async def test_card_edited_in_one_browser_shows_live_in_another(
    user, create_user, live_services, supabase_client, created_session_ids
):
    app.deps.services = live_services
    sid = new_session_id()
    await Repository(supabase_client).create_session("IT edit " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)
    session = await live_services.sessions.get(sid)
    assert session is not None
    quadrant = next(q for q in session.quadrants if q.kind == "IS")

    token = secrets.token_hex(4)
    before, after = f"Before {token}", f"After {token}"
    card = await live_services.sessions.add_card(session.workspace_id, quadrant.id, before, "Ann")

    # The NiceGUI test plugin runs a handler under the most recently opened request's storage,
    # so the second browser opens first and the acting browser last.
    second = create_user()
    await second.open(f"/s/{sid}")
    await user.open(f"/s/{sid}")
    with second.scope(marker="cards-IS"):
        await second.should_see(before, retries=50)

    marker = f"card-{card.id}"
    with user.scope(marker=marker):
        user.find(marker="card-text").click()
        user.find(marker="card-editor").clear().type(after)
        started = time.monotonic()
        user.find(marker="card-editor").trigger("keydown.enter.exact.prevent")
    with user.scope(marker="cards-IS"):
        await user.should_see(after, retries=50)  # at once, for the actor
    await user.should_not_see(marker="card-editor")  # saved: the editor closed

    with second.scope(marker=marker):
        await second.should_see(after, retries=50)  # within about 1 s, no reload
        await second.should_see("(edited)", retries=50)
    elapsed = time.monotonic() - started
    print(f"\nLIVE: edit Enter -> browser B shows the edit: {elapsed * 1000:.0f} ms")

    # CARD-08: confirmation and echo have both arrived; the card was updated in place.
    elements = user.find(marker=marker).elements
    assert len(elements) == 1
    assert next(iter(elements)).default_slot.children[0].text == after

    resp = await supabase_client.table("cards").select("*").eq("id", card.id).execute()
    assert len(resp.data) == 1
    row = resp.data[0]
    assert row["text"] == after
    assert row["author"] == "Ann"  # D-05: an edit never changes the author
    assert row["text_updated_at"] is not None
    stamped = datetime.fromisoformat(row["text_updated_at"])
    assert stamped == datetime.fromisoformat(row["updated_at"])  # stamped by the trigger
    assert datetime.fromisoformat(row["updated_at"]) > datetime.fromisoformat(row["created_at"])
    # D-05: edit_card writes only text.
    assert row["workspace_id"] == card.workspace_id
    assert row["quadrant_id"] == card.quadrant_id
    assert row["order_index"] == card.order_index
    assert datetime.fromisoformat(row["created_at"]) == card.created_at
