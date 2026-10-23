"""Live proof against hosted Supabase: a card edited in one browser shows live in another.

Tracer for Phase 3 (CARD-02, CARD-08): click the card text, edit it inline, press Enter. The
row is written by ``SessionService.edit_card``, the ``cards_touch`` trigger stamps ``updated_at``
and ``text_updated_at``, and the Realtime echo updates the card in place in both browsers.

D-04 (03-03): a draft one participant has open survives another participant's edit of the same
card, and when that participant saves, their text is the last save and wins everywhere.
"""

import asyncio
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


ENTER = "keydown.enter.exact.prevent"


def _hidden_label_text(browser, marker: str) -> str:
    """The card's first child: its text label (hidden while an editor is open in it)."""
    (card,) = browser.find(marker=marker).elements
    return card.default_slot.children[0].text


@pytest.mark.integration
async def test_open_draft_survives_remote_edit_and_last_save_wins(
    user, create_user, live_services, supabase_client, created_session_ids
):
    app.deps.services = live_services
    sid = new_session_id()
    await Repository(supabase_client).create_session("IT draft " + secrets.token_hex(4), sid)
    created_session_ids.append(sid)
    session = await live_services.sessions.get(sid)
    assert session is not None
    quadrant = next(q for q in session.quadrants if q.kind == "IS")

    token = secrets.token_hex(4)
    base, a_text, b_draft = f"Base {token}", f"A text {token}", f"B draft {token}"
    card = await live_services.sessions.add_card(session.workspace_id, quadrant.id, base, "Ann")
    marker = f"card-{card.id}"

    # B opens first and A, the acting browser, last (storage of the most recent request).
    browser_b = create_user()
    await browser_b.open(f"/s/{sid}")
    await user.open(f"/s/{sid}")
    with browser_b.scope(marker="cards-IS"):
        await browser_b.should_see(base, retries=50)

    # B starts editing and types a draft; nothing is saved.
    with browser_b.scope(marker=marker):
        browser_b.find(marker="card-text").click()
    browser_b.find(marker="card-editor").clear().type(b_draft)
    (editor_b,) = browser_b.find(marker="card-editor").elements

    # A edits the same card and saves.
    started_a = time.monotonic()
    with user.scope(marker=marker):
        user.find(marker="card-text").click()
        user.find(marker="card-editor").clear().type(a_text)
        user.find(marker="card-editor").trigger(ENTER)
    with user.scope(marker="cards-IS"):
        await user.should_see(a_text, retries=50)

    # B's hidden label follows A's text through the Realtime echo; B's editor is untouched.
    # The loop only reads this test browser's elements; the app itself has no loop or timer.
    for _ in range(50):
        if _hidden_label_text(browser_b, marker) == a_text:
            break
        await asyncio.sleep(0.1)
    assert _hidden_label_text(browser_b, marker) == a_text
    follow_ms = (time.monotonic() - started_a) * 1000
    print(f"\nLIVE: A Enter -> B's hidden label follows: {follow_ms:.0f} ms")
    (still_editor_b,) = browser_b.find(marker="card-editor").elements
    assert still_editor_b is editor_b
    assert editor_b.value == b_draft

    # B saves: the last save wins on every screen and in the database.
    started = time.monotonic()
    browser_b.find(marker="card-editor").trigger(ENTER)
    for _ in range(50):
        if _hidden_label_text(user, marker) == b_draft:
            break
        await asyncio.sleep(0.1)
    elapsed = time.monotonic() - started
    assert _hidden_label_text(user, marker) == b_draft
    print(f"\nLIVE: draft kept, B Enter -> browser A shows B's text: {elapsed * 1000:.0f} ms")
    await browser_b.should_not_see(marker="card-editor")
    assert _hidden_label_text(browser_b, marker) == b_draft

    resp = await supabase_client.table("cards").select("*").eq("id", card.id).execute()
    assert len(resp.data) == 1
    assert resp.data[0]["text"] == b_draft
    assert resp.data[0]["author"] == "Ann"
