"""Card rendering on the canvas: snapshot on open, single rendering, Realtime-only delivery.

NiceGUI's test plugin runs a click handler under the storage of the most recently opened
request, so when two browsers are open the acting (named) browser is opened last.
"""

from datetime import datetime

from app.deps import get_services
from app.ui.canvas_view import format_card_time
from tests.ui.fakes import (
    SEEDED_ID_A,
    SEEDED_ID_B,
    SEEDED_NAME_A,
    SEEDED_NAME_B,
    card_event,
    install_fake_services,
    seed_card,
)

PATH_A = f"/s/{SEEDED_ID_A}"
PATH_B = f"/s/{SEEDED_ID_B}"
EMPTY = "No cards yet"


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


async def _save_name(browser, name: str) -> None:
    browser.find(marker="name-input").clear().type(name)
    browser.find("Save").click()
    await browser.should_see(marker="display-name", content=name)


async def _workspace_id(session_id: str) -> str:
    view = await get_services().sessions.get(session_id)
    assert view is not None
    return view.workspace_id


async def test_reopened_canvas_shows_stored_cards_in_order(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "later", created_at="2026-10-23T10:00:05+00:00")
    seed_card(repo, SEEDED_ID_A, "IS", "earlier", created_at="2026-10-23T10:00:01+00:00")
    seed_card(repo, SEEDED_ID_A, "DOES", "does card")

    await user.open(PATH_A)

    assert _card_texts(user, "IS") == ["earlier", "later"]
    assert _card_texts(user, "DOES") == ["does card"]
    for kind in ("IS", "DOES"):
        with user.scope(marker=f"quadrant-{kind}"):
            await user.should_not_see(EMPTY)
    for kind in ("IS_NOT", "DOES_NOT"):
        with user.scope(marker=f"quadrant-{kind}"):
            await user.should_see(EMPTY)


async def test_soft_deleted_rows_are_not_shown_on_open(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "visible card")
    seed_card(repo, SEEDED_ID_A, "IS", "removed card", deleted_at="2026-10-23T10:00:00+00:00")

    await user.open(PATH_A)

    await user.should_see("visible card")
    await user.should_not_see("removed card")
    assert _card_texts(user, "IS") == ["visible card"]


async def test_own_card_renders_once_even_after_echo(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)
    await _save_name(user, "Ann")

    user.find(marker="add-input-IS").type("Hello")
    user.find(marker="add-button-IS").click()
    with user.scope(marker="cards-IS"):
        await user.should_see("Hello", retries=50)

    (row,) = repo.cards.values()
    get_services().hub._on_card(card_event(row))  # the Realtime echo of the same stored row

    assert _card_texts(user, "IS") == ["Hello"]
    assert len(user.find(marker="card").elements) == 1


async def test_other_browser_sees_card_only_after_realtime_event(user, create_user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    other = create_user()
    await other.open(PATH_A)
    await user.open(PATH_A)
    await _save_name(user, "Ann")

    user.find(marker="add-input-DOES").type("Shared card")
    user.find(marker="add-button-DOES").click()
    with user.scope(marker="cards-DOES"):
        await user.should_see("Shared card", retries=50)

    # No in-process shortcut: the other browser has nothing until the hub gets the event.
    await other.should_not_see("Shared card")
    assert _card_texts(other, "DOES") == []

    (row,) = repo.cards.values()
    get_services().hub._on_card(card_event(row))

    with other.scope(marker="quadrant-DOES"):
        await other.should_see("Shared card")
        expected = format_card_time(datetime.fromisoformat(row["created_at"]))
        await other.should_see(marker="card-meta", content=f"Ann · {expected}")
    assert _card_texts(other, "DOES") == ["Shared card"]


async def test_event_for_another_session_is_not_rendered(user, create_user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    page_b = create_user()
    await page_b.open(PATH_B)
    await user.open(PATH_A)

    row = seed_card(repo, SEEDED_ID_B, "IS", "only for B")
    assert row["workspace_id"] == await _workspace_id(SEEDED_ID_B)
    get_services().hub._on_card(card_event(row))

    await page_b.should_see("only for B")
    await user.should_not_see("only for B")
    assert _card_texts(user, "IS") == []


async def test_listener_unregistered_when_client_deleted(user):
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    hub = get_services().hub
    workspace_id = await _workspace_id(SEEDED_ID_A)

    await user.open(PATH_A)
    assert hub.listener_count(workspace_id) == 1

    user.client.delete()
    assert hub.listener_count(workspace_id) == 0
