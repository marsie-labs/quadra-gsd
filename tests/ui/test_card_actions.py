"""Card actions from the card menu: Delete (Task 1) and Move to (Task 2), with optimistic UI.

NiceGUI's test plugin runs a handler under the storage of the most recently opened request; every
UI test here uses a single browser. Offline: the REAL SessionService and CanvasView run over the
in-memory ``FakeRepository``, whose ``_touch`` mirrors the ``cards_touch`` trigger.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from nicegui import ui
from nicegui.testing.user_notify import UserNotify
from postgrest.exceptions import APIError

from app.deps import get_services
from app.services.sessions import CardGone
from app.ui import canvas_view as cv
from tests.ui.fakes import (
    SEEDED_ID_A,
    SEEDED_ID_B,
    SEEDED_NAME_A,
    SEEDED_NAME_B,
    card_event,
    install_fake_services,
    seed_card,
    soft_delete_card,
)

PATH_A = f"/s/{SEEDED_ID_A}"
DIALOG_TITLE = "Enter your name to continue"


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


def _menu_button(browser, card_id: str) -> ui.button:
    with browser.scope(marker=f"card-{card_id}"):
        return next(iter(browser.find(marker="card-menu").elements))


def _menu_items(browser, card_id: str) -> list[ui.element]:
    """The top-level items of one card's menu, in order (they exist while the menu is closed)."""
    menu = next(
        e for e in _menu_button(browser, card_id).default_slot.children if e.tag == "q-menu"
    )
    return list(menu.default_slot.children)


def _item_text(item: ui.element) -> str:
    return item.default_slot.children[0].text


def _delete(browser, card_id: str) -> None:
    with browser.scope(marker=f"card-{card_id}"):
        browser.find(marker="card-action-delete").click()


async def _wait_for(predicate, retries: int = 100) -> None:
    for _ in range(retries):
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


class _TypedNotify(UserNotify):
    """The simulated user's notify, also remembering each message's notification type."""

    def __init__(self) -> None:
        super().__init__()
        self.typed: list[tuple[str, str | None]] = []

    def __call__(self, message: str, **kwargs) -> None:
        self.typed.append((message, kwargs.get("type")))
        super().__call__(message, **kwargs)


def test_user_facing_messages_are_pinned():
    assert cv.CARD_DELETED == "Card deleted"
    assert cv.DELETE_FAILED == "Could not delete the card. Please try again."


# ---------------------------------------------------------------- delete: fake and service


async def test_fake_soft_delete_stamps_deleted_at_keeps_the_row_and_is_idempotent():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed")
    sessions = get_services().sessions

    deleted = await sessions.delete_card(row["workspace_id"], row["id"])

    assert deleted is not None
    assert deleted.deleted_at is not None
    assert deleted.updated_at > datetime.fromisoformat(row["updated_at"])
    assert deleted.text == "doomed"
    assert deleted.author == "Ann"
    assert row["id"] in repo.cards  # soft delete: the row stays
    first_deleted_at = repo.cards[row["id"]]["deleted_at"]

    again = await sessions.delete_card(row["workspace_id"], row["id"])

    assert again is None
    assert repo.cards[row["id"]]["deleted_at"] == first_deleted_at
    assert repo.update_calls == 2


async def test_delete_card_of_another_session_or_unknown_id_returns_none_and_changes_nothing():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    mine = seed_card(repo, SEEDED_ID_A, "IS", "mine")
    foreign_workspace = repo.rows[SEEDED_ID_B]["id"]
    sessions = get_services().sessions

    assert await sessions.delete_card(foreign_workspace, mine["id"]) is None
    assert (
        await sessions.delete_card(mine["workspace_id"], "00000000-0000-0000-0000-000000000000")
        is None
    )
    assert repo.cards[mine["id"]]["deleted_at"] is None


# ---------------------------------------------------------------- delete: in the browser


async def test_delete_is_the_last_menu_item_with_its_marker(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "alpha")
    await user.open(PATH_A)

    items = _menu_items(user, row["id"])

    assert _item_text(items[-1]) == "Delete"
    assert "card-action-delete" in items[-1]._markers


async def test_delete_removes_the_card_at_once_with_a_toast_and_soft_deletes(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed")
    keep = seed_card(repo, SEEDED_ID_A, "IS", "keeper", order_index=2048.0)
    await user.open(PATH_A)
    hub = get_services().hub
    repo.update_gate = asyncio.Event()

    _delete(user, row["id"])
    await _wait_for(lambda: repo.update_calls == 1)

    # The write is held: the card is already gone for the actor, the row is untouched.
    assert _card_texts(user, "IS") == ["keeper"]
    await user.should_see(cv.CARD_DELETED)
    assert repo.cards[row["id"]]["deleted_at"] is None

    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[row["id"]]["deleted_at"] is not None)
    await asyncio.sleep(0.1)  # let the confirmed row reach the page

    # The Realtime echo of our own delete changes nothing and raises nothing.
    echo = dict(repo.cards[row["id"]])
    hub._on_card(card_event(echo, "UPDATE", old=row))
    assert _card_texts(user, "IS") == ["keeper"]
    assert row["id"] in repo.cards  # never a hard delete
    assert repo.cards[keep["id"]]["deleted_at"] is None


async def test_deleting_the_only_card_of_a_quadrant_shows_the_empty_hint_again(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "alone")
    await user.open(PATH_A)
    with user.scope(marker="quadrant-IS"):
        await user.should_not_see("No cards yet")

    _delete(user, row["id"])

    await _wait_for(lambda: repo.cards[row["id"]]["deleted_at"] is not None)
    with user.scope(marker="quadrant-IS"):
        await user.should_see("No cards yet")


async def test_failed_delete_brings_the_card_back_between_its_neighbours(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "a", order_index=1024.0)
    middle = seed_card(repo, SEEDED_ID_A, "IS", "b", order_index=2048.0)
    seed_card(repo, SEEDED_ID_A, "IS", "c", order_index=3072.0)
    repo.fail_next_update_codes = ["XX000"]
    await user.open(PATH_A)
    user.notify = notifications = _TypedNotify()

    _delete(user, middle["id"])

    await user.should_see(cv.DELETE_FAILED)
    assert (cv.DELETE_FAILED, "negative") in notifications.typed
    await _wait_for(lambda: _card_texts(user, "IS") == ["a", "b", "c"])
    assert repo.cards[middle["id"]]["deleted_at"] is None


async def test_two_delete_clicks_before_the_write_returns_write_once(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed")
    await user.open(PATH_A)
    repo.update_gate = asyncio.Event()

    _delete(user, row["id"])
    _delete(user, row["id"])  # both clicks land before either handler task has run
    await _wait_for(lambda: repo.update_calls >= 1)
    await asyncio.sleep(0.1)

    assert repo.update_calls == 1
    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[row["id"]]["deleted_at"] is not None)
    await asyncio.sleep(0.1)
    assert repo.update_calls == 1


async def test_deleting_a_card_already_deleted_elsewhere_is_quiet_and_it_stays_gone(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed")
    await user.open(PATH_A)
    user.notify = notifications = _TypedNotify()

    soft_delete_card(repo, row["id"])  # deleted elsewhere, no event reached this page
    _delete(user, row["id"])

    await _wait_for(lambda: repo.update_calls == 1)
    await asyncio.sleep(0.1)
    assert _card_texts(user, "IS") == []
    messages = [message for message, _ in notifications.typed]
    assert cv.DELETE_FAILED not in messages
    assert not any(kind == "negative" for _, kind in notifications.typed)


async def test_anyone_deletes_without_a_name_and_the_dialog_stays_closed(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed", author="Ann")
    await user.open(PATH_A)
    await user.should_see(marker="name-banner")

    _delete(user, row["id"])

    await _wait_for(lambda: repo.cards[row["id"]]["deleted_at"] is not None)
    await user.should_not_see(DIALOG_TITLE)
    await user.should_see(marker="name-banner")
    assert repo.cards[row["id"]]["author"] == "Ann"


async def test_delete_never_changes_text_or_author(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed", author="Ann")
    await user.open(PATH_A)

    _delete(user, row["id"])

    await _wait_for(lambda: repo.cards[row["id"]]["deleted_at"] is not None)
    stored = repo.cards[row["id"]]
    assert stored["text"] == "doomed"
    assert stored["author"] == "Ann"
    assert stored["text_updated_at"] is None
    assert repo.update_calls == 1
    assert datetime.fromisoformat(stored["deleted_at"]) <= datetime.now(UTC)


# ================================================================ Move to

KINDS = ("IS", "IS_NOT", "DOES", "DOES_NOT")
LABELS = {"IS": "IS", "IS_NOT": "IS NOT", "DOES": "DOES", "DOES_NOT": "DOES NOT"}


def _quadrant_id(repo, session_id: str, kind: str) -> str:
    return next(q["id"] for q in repo.rows[session_id]["quadrants"] if q["kind"] == kind)


def _card_element(browser, card_id: str) -> ui.card:
    return next(iter(browser.find(marker=f"card-{card_id}").elements))


def _card_count(browser) -> int:
    columns = [next(iter(browser.find(marker=f"cards-{kind}").elements)) for kind in KINDS]
    return sum(len(column.default_slot.children) for column in columns)


def _move(browser, card_id: str, kind: str) -> None:
    with browser.scope(marker=f"card-{card_id}"):
        browser.find(marker=f"card-action-move-{kind}").click()


def _meta(browser, card_id: str) -> str:
    with browser.scope(marker=f"card-{card_id}"):
        return next(iter(browser.find(marker="card-meta").elements)).text


def test_move_messages_are_pinned():
    assert cv.MOVE_FAILED == "Could not move the card. Please try again."


# ---------------------------------------------------------------- move: fake and service


async def test_move_card_goes_to_the_end_of_the_target_and_keeps_text_author_and_edit_state():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover", author="Bea")
    seed_card(repo, SEEDED_ID_A, "DOES", "first", order_index=1024.0)
    seed_card(repo, SEEDED_ID_A, "DOES", "second", order_index=2048.0)
    does = _quadrant_id(repo, SEEDED_ID_A, "DOES")

    moved = await get_services().sessions.move_card(mover["workspace_id"], mover["id"], does)

    assert moved.quadrant_id == does
    assert moved.order_index == 3072.0
    assert moved.text == "mover"
    assert moved.author == "Bea"
    assert moved.text_updated_at is None
    assert moved.updated_at > datetime.fromisoformat(mover["updated_at"])
    assert repo.cards[mover["id"]]["deleted_at"] is None


async def test_move_card_into_an_empty_quadrant_gets_the_first_slot():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover", order_index=5000.0)
    target = _quadrant_id(repo, SEEDED_ID_A, "DOES_NOT")

    moved = await get_services().sessions.move_card(mover["workspace_id"], mover["id"], target)

    assert moved.order_index == 1024.0


async def test_move_card_ignores_soft_deleted_cards_when_finding_the_end():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover")
    seed_card(repo, SEEDED_ID_A, "DOES", "kept", order_index=1024.0)
    gone = seed_card(repo, SEEDED_ID_A, "DOES", "gone", order_index=9000.0)
    soft_delete_card(repo, gone["id"])
    does = _quadrant_id(repo, SEEDED_ID_A, "DOES")

    moved = await get_services().sessions.move_card(mover["workspace_id"], mover["id"], does)

    assert moved.order_index == 2048.0


async def test_move_into_a_quadrant_of_another_session_is_rejected_and_changes_nothing():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover")
    foreign = _quadrant_id(repo, SEEDED_ID_B, "DOES")

    with pytest.raises(APIError) as rejected:
        await get_services().sessions.move_card(mover["workspace_id"], mover["id"], foreign)

    assert rejected.value.code == "23503"
    assert repo.cards[mover["id"]] == mover


async def test_move_card_that_is_deleted_or_unknown_raises_card_gone():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    gone = seed_card(repo, SEEDED_ID_A, "IS", "gone")
    soft_delete_card(repo, gone["id"])
    does = _quadrant_id(repo, SEEDED_ID_A, "DOES")
    sessions = get_services().sessions

    with pytest.raises(CardGone):
        await sessions.move_card(gone["workspace_id"], gone["id"], does)
    with pytest.raises(CardGone):
        await sessions.move_card(gone["workspace_id"], "00000000-0000-0000-0000-000000000000", does)


# ---------------------------------------------------------------- move: in the browser


async def test_menu_holds_edit_then_move_to_then_delete(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "alpha")
    await user.open(PATH_A)

    items = _menu_items(user, row["id"])

    assert [_item_text(item) for item in items] == ["Edit", "Move to", "Delete"]
    assert "card-action-move" in items[1]._markers


async def test_move_to_offers_the_three_other_quadrants_by_label(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "alpha")
    await user.open(PATH_A)

    with user.scope(marker=f"card-{row['id']}"):
        for kind in ("IS_NOT", "DOES", "DOES_NOT"):
            (item,) = user.find(marker=f"card-action-move-{kind}").elements
            assert item.default_slot.children[0].text == LABELS[kind]
        await user.should_not_see(marker="card-action-move-IS")


async def test_move_goes_to_the_end_of_the_target_at_once_and_the_old_quadrant_empties(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover")
    seed_card(repo, SEEDED_ID_A, "DOES", "first", order_index=1024.0)
    seed_card(repo, SEEDED_ID_A, "DOES", "second", order_index=2048.0)
    await user.open(PATH_A)
    repo.update_gate = asyncio.Event()

    _move(user, mover["id"], "DOES")
    await _wait_for(lambda: repo.update_calls == 1)

    # The write is held: the card already sits last in DOES and IS is empty again.
    assert _card_texts(user, "DOES") == ["first", "second", "mover"]
    assert _card_texts(user, "IS") == []
    with user.scope(marker="quadrant-IS"):
        await user.should_see("No cards yet")
    assert repo.cards[mover["id"]]["quadrant_id"] == _quadrant_id(repo, SEEDED_ID_A, "IS")

    repo.update_gate.set()
    await _wait_for(
        lambda: repo.cards[mover["id"]]["quadrant_id"] != _quadrant_id(repo, SEEDED_ID_A, "IS")
    )
    stored = repo.cards[mover["id"]]
    assert stored["quadrant_id"] == _quadrant_id(repo, SEEDED_ID_A, "DOES")
    assert stored["order_index"] == 3072.0


async def test_after_a_move_the_menu_offers_the_old_quadrant_and_hides_the_new_one(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover")
    await user.open(PATH_A)

    _move(user, mover["id"], "DOES")
    await _wait_for(lambda: _card_texts(user, "DOES") == ["mover"])
    await asyncio.sleep(0.1)

    with user.scope(marker=f"card-{mover['id']}"):
        await user.should_see(marker="card-action-move-IS")
        await user.should_not_see(marker="card-action-move-DOES")


async def test_the_card_element_survives_the_move_and_the_echo_shows_it_once(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover")
    await user.open(PATH_A)
    hub = get_services().hub
    element_before = _card_element(user, mover["id"])

    _move(user, mover["id"], "DOES")
    does = _quadrant_id(repo, SEEDED_ID_A, "DOES")
    await _wait_for(lambda: repo.cards[mover["id"]]["quadrant_id"] == does)
    await asyncio.sleep(0.1)  # let the confirmed row reach the page
    hub._on_card(card_event(dict(repo.cards[mover["id"]]), "UPDATE", old=mover))  # our own echo

    assert _card_count(user) == 1
    assert _card_texts(user, "DOES") == ["mover"]
    assert _card_element(user, mover["id"]) is element_before


async def test_failed_move_puts_the_card_back_at_its_old_position(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "a", order_index=1024.0)
    middle = seed_card(repo, SEEDED_ID_A, "IS", "b", order_index=2048.0)
    seed_card(repo, SEEDED_ID_A, "IS", "c", order_index=3072.0)
    repo.fail_next_update_codes = ["XX000"]
    await user.open(PATH_A)
    user.notify = notifications = _TypedNotify()

    _move(user, middle["id"], "DOES")

    await user.should_see(cv.MOVE_FAILED)
    assert (cv.MOVE_FAILED, "negative") in notifications.typed
    await _wait_for(lambda: _card_texts(user, "IS") == ["a", "b", "c"])
    assert _card_texts(user, "DOES") == []
    assert repo.cards[middle["id"]]["quadrant_id"] == _quadrant_id(repo, SEEDED_ID_A, "IS")


async def test_moving_never_adds_edited_and_keeps_the_author(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover", author="Bea")
    await user.open(PATH_A)

    _move(user, mover["id"], "DOES_NOT")
    does_not = _quadrant_id(repo, SEEDED_ID_A, "DOES_NOT")
    await _wait_for(lambda: repo.cards[mover["id"]]["quadrant_id"] == does_not)
    await asyncio.sleep(0.1)

    assert "(edited)" not in _meta(user, mover["id"])
    assert _meta(user, mover["id"]).startswith("Bea")
    assert repo.cards[mover["id"]]["author"] == "Bea"
    assert repo.cards[mover["id"]]["text"] == "mover"


async def test_two_move_clicks_before_the_write_returns_write_once(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover")
    await user.open(PATH_A)
    repo.update_gate = asyncio.Event()

    _move(user, mover["id"], "DOES")
    _move(user, mover["id"], "DOES_NOT")  # both clicks land before either handler task has run
    await _wait_for(lambda: repo.update_calls >= 1)
    await asyncio.sleep(0.1)

    assert repo.update_calls == 1
    repo.update_gate.set()
    await asyncio.sleep(0.1)
    assert repo.update_calls == 1
    assert repo.cards[mover["id"]]["quadrant_id"] == _quadrant_id(repo, SEEDED_ID_A, "DOES")


async def test_anyone_moves_without_a_name_and_the_dialog_stays_closed(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    mover = seed_card(repo, SEEDED_ID_A, "IS", "mover", author="Ann")
    await user.open(PATH_A)
    await user.should_see(marker="name-banner")

    _move(user, mover["id"], "IS_NOT")

    is_not = _quadrant_id(repo, SEEDED_ID_A, "IS_NOT")
    await _wait_for(lambda: repo.cards[mover["id"]]["quadrant_id"] == is_not)
    await user.should_not_see(DIALOG_TITLE)
    await user.should_see(marker="name-banner")
    assert repo.cards[mover["id"]]["author"] == "Ann"
