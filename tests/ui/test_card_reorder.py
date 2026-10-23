"""Reordering a card up or down inside its quadrant (CARD-05, CARD-08).

Three layers in one file, as ``tests/unit/test_card_rules.py`` keeps pure rules next to service
tests: the pure ``reorder_index`` rule, ``SessionService.reorder_card`` over the in-memory
``FakeRepository``, and the card menu in a simulated browser. NiceGUI's test plugin runs a handler
under the storage of the most recently opened request, so every UI test here uses one browser.
"""

import asyncio
import math
from datetime import UTC, datetime

import pytest
from nicegui import ui
from nicegui.testing.user_notify import UserNotify

from app.deps import get_services
from app.services import sessions as svc
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

# ================================================================ the pure rule

THREE = [("a", 1024.0), ("b", 2048.0), ("c", 3072.0)]


@pytest.mark.parametrize(
    ("ordered", "card_id", "direction", "expected"),
    [
        (THREE, "c", "up", 1536.0),
        (THREE, "b", "up", 0.0),
        (THREE, "a", "up", None),
        (THREE, "a", "down", 2560.0),
        (THREE, "b", "down", 4096.0),
        (THREE, "c", "down", None),
        (THREE, "zz", "up", None),
        ([("a", 1024.0)], "a", "up", None),
        ([("a", 1024.0)], "a", "down", None),
        # Ties: the card passes the whole tie group; the bound is the next strictly different value.
        ([("a", 1024.0), ("b", 2048.0), ("p", 2048.0), ("c", 3072.0)], "c", "up", 1536.0),
        ([("c", 1024.0), ("n", 1024.0), ("x", 2048.0)], "c", "down", 1536.0),
        ([("p", 1024.0), ("c", 1024.0)], "c", "up", 0.0),
        # Exhaustion: no double fits strictly between two adjacent floats.
        ([("a", 1.0), ("b", math.nextafter(1.0, 2.0)), ("c", 5.0)], "c", "up", None),
        ([("a", -1024.0), ("b", -512.0), ("c", 0.0)], "c", "up", -768.0),
    ],
)
def test_reorder_index_places_the_card_between_its_new_neighbours(
    ordered, card_id, direction, expected
):
    assert svc.reorder_index(ordered, card_id, direction) == expected


# ================================================================ the service over the fake


def _is_card_ids(repo) -> list[str]:
    rows = [c for c in repo.cards.values() if c["deleted_at"] is None]
    return [c["id"] for c in sorted(rows, key=lambda c: (c["order_index"], c["created_at"]))]


async def test_reorder_card_writes_once_and_changes_only_the_moved_order_index():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a = seed_card(repo, SEEDED_ID_A, "IS", "a", order_index=1024.0)
    b = seed_card(repo, SEEDED_ID_A, "IS", "b", order_index=2048.0)
    c = seed_card(repo, SEEDED_ID_A, "IS", "c", author="Cy", order_index=3072.0)

    moved = await get_services().sessions.reorder_card(c["workspace_id"], c["id"], "up")

    assert repo.update_calls == 1
    assert moved.order_index == 1536.0
    assert repo.cards[c["id"]]["order_index"] == 1536.0
    assert repo.cards[a["id"]] == a  # order_index and updated_at both identical
    assert repo.cards[b["id"]] == b
    stored = repo.cards[c["id"]]
    assert stored["text"] == "c"
    assert stored["author"] == "Cy"
    assert stored["text_updated_at"] is None
    assert datetime.fromisoformat(stored["updated_at"]) > datetime.fromisoformat(c["updated_at"])


async def test_reorder_card_at_the_edge_writes_nothing_and_returns_the_card_unchanged():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    first = seed_card(repo, SEEDED_ID_A, "IS", "first", order_index=1024.0)
    last = seed_card(repo, SEEDED_ID_A, "IS", "last", order_index=2048.0)
    sessions = get_services().sessions

    up = await sessions.reorder_card(first["workspace_id"], first["id"], "up")
    down = await sessions.reorder_card(last["workspace_id"], last["id"], "down")

    assert repo.update_calls == 0
    assert up.id == first["id"] and up.order_index == 1024.0
    assert down.id == last["id"] and down.order_index == 2048.0
    assert repo.cards[first["id"]] == first
    assert repo.cards[last["id"]] == last


async def test_reorder_card_decides_from_the_database_not_from_the_browser():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a = seed_card(repo, SEEDED_ID_A, "IS", "a", order_index=1024.0)
    c = seed_card(repo, SEEDED_ID_A, "IS", "c", order_index=2048.0)
    b = seed_card(repo, SEEDED_ID_A, "IS", "b", order_index=3072.0)

    # In the database c sits second, so "up" passes a: below its order_index minus the gap.
    moved = await get_services().sessions.reorder_card(c["workspace_id"], c["id"], "up")

    assert moved.order_index == 0.0
    assert _is_card_ids(repo) == [c["id"], a["id"], b["id"]]


async def test_reorder_card_of_a_deleted_unknown_or_foreign_card_raises_card_gone():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    gone = seed_card(repo, SEEDED_ID_A, "IS", "gone")
    seed_card(repo, SEEDED_ID_A, "IS", "keeper", order_index=2048.0)
    soft_delete_card(repo, gone["id"])
    mine = seed_card(repo, SEEDED_ID_A, "IS", "mine", order_index=3072.0)
    foreign_workspace = repo.rows[SEEDED_ID_B]["id"]
    sessions = get_services().sessions

    with pytest.raises(CardGone):
        await sessions.reorder_card(gone["workspace_id"], gone["id"], "up")
    with pytest.raises(CardGone):
        await sessions.reorder_card(
            gone["workspace_id"], "00000000-0000-0000-0000-000000000000", "up"
        )
    with pytest.raises(CardGone):
        await sessions.reorder_card(foreign_workspace, mine["id"], "up")

    assert repo.cards[mine["id"]] == mine


async def test_reorder_card_rejects_an_unknown_direction_before_any_read():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "a")

    with pytest.raises(ValueError):
        await get_services().sessions.reorder_card(row["workspace_id"], row["id"], "sideways")  # type: ignore[arg-type]

    assert repo.update_calls == 0


# ================================================================ the card menu


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


def _menu_items(browser, card_id: str) -> list[ui.element]:
    with browser.scope(marker=f"card-{card_id}"):
        button = next(iter(browser.find(marker="card-menu").elements))
    menu = next(e for e in button.default_slot.children if e.tag == "q-menu")
    return list(menu.default_slot.children)


def _item_text(item: ui.element) -> str:
    return item.default_slot.children[0].text


def _enabled(browser, card_id: str, which: str) -> bool:
    with browser.scope(marker=f"card-{card_id}"):
        (item,) = browser.find(marker=f"card-action-{which}").elements
    return item.enabled


def _states(browser, card_id: str) -> tuple[bool, bool]:
    return _enabled(browser, card_id, "up"), _enabled(browser, card_id, "down")


def _reorder(browser, card_id: str, which: str) -> None:
    with browser.scope(marker=f"card-{card_id}"):
        browser.find(marker=f"card-action-{which}").click()


def _card_element(browser, card_id: str) -> ui.card:
    return next(iter(browser.find(marker=f"card-{card_id}").elements))


def _meta(browser, card_id: str) -> str:
    with browser.scope(marker=f"card-{card_id}"):
        return next(iter(browser.find(marker="card-meta").elements)).text


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


def _three_cards(repo):
    a = seed_card(repo, SEEDED_ID_A, "IS", "a", order_index=1024.0)
    b = seed_card(repo, SEEDED_ID_A, "IS", "b", order_index=2048.0)
    c = seed_card(repo, SEEDED_ID_A, "IS", "c", order_index=3072.0)
    return a, b, c


async def test_menu_holds_edit_move_to_move_up_move_down_delete_in_that_order(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "alpha")
    await user.open(PATH_A)

    items = _menu_items(user, row["id"])

    assert [_item_text(item) for item in items] == [
        "Edit",
        "Move to",
        "Move up",
        "Move down",
        "Delete",
    ]
    assert "card-action-up" in items[2]._markers
    assert "card-action-down" in items[3]._markers


async def test_edge_items_are_disabled_and_stay_in_the_menu(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    await user.open(PATH_A)

    assert _states(user, a["id"]) == (False, True)
    assert _states(user, b["id"]) == (True, True)
    assert _states(user, c["id"]) == (True, False)


async def test_a_single_card_has_both_items_disabled(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    only = seed_card(repo, SEEDED_ID_A, "IS", "only")
    await user.open(PATH_A)

    assert _states(user, only["id"]) == (False, False)
    assert len(_menu_items(user, only["id"])) == 5  # disabled, not removed


async def test_move_up_swaps_at_once_keeps_the_card_element_and_writes_one_row(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    await user.open(PATH_A)
    element_before = _card_element(user, c["id"])
    repo.update_gate = asyncio.Event()

    _reorder(user, c["id"], "up")
    await _wait_for(lambda: repo.update_calls == 1)

    # The write is held: the actor already sees a, c, b; the database still has the old order.
    assert _card_texts(user, "IS") == ["a", "c", "b"]
    assert _card_element(user, c["id"]) is element_before
    assert repo.cards[c["id"]]["order_index"] == 3072.0

    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[c["id"]]["order_index"] == 1536.0)
    await asyncio.sleep(0.1)  # let the confirmed row reach the page

    assert _card_texts(user, "IS") == ["a", "c", "b"]
    assert _card_element(user, c["id"]) is element_before
    assert repo.update_calls == 1
    assert repo.cards[a["id"]] == a and repo.cards[b["id"]] == b


async def test_move_down_swaps_with_the_next_card(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    await user.open(PATH_A)

    _reorder(user, a["id"], "down")

    await _wait_for(lambda: repo.cards[a["id"]]["order_index"] == 2560.0)
    assert _card_texts(user, "IS") == ["b", "a", "c"]


async def test_enabled_states_follow_the_new_order_after_a_move(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    await user.open(PATH_A)

    _reorder(user, c["id"], "up")
    await _wait_for(lambda: repo.cards[c["id"]]["order_index"] == 1536.0)
    await asyncio.sleep(0.1)

    # The order is now a, c, b.
    assert _states(user, a["id"]) == (False, True)
    assert _states(user, c["id"]) == (True, True)
    assert _states(user, b["id"]) == (True, False)


async def test_a_remote_insert_at_the_end_enables_move_down_on_the_previous_last_card(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    await user.open(PATH_A)
    assert _enabled(user, c["id"], "down") is False

    fresh = seed_card(repo, SEEDED_ID_A, "IS", "d", order_index=4096.0)
    get_services().hub._on_card(card_event(fresh, "INSERT"))

    await _wait_for(lambda: _card_texts(user, "IS") == ["a", "b", "c", "d"])
    assert _enabled(user, c["id"], "down") is True
    assert _states(user, fresh["id"]) == (True, False)


async def test_a_remote_move_out_of_the_quadrant_updates_the_remaining_cards(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    await user.open(PATH_A)
    does = next(q["id"] for q in repo.rows[SEEDED_ID_A]["quadrants"] if q["kind"] == "DOES")

    moved_away = {**c, "quadrant_id": does, "updated_at": datetime.now(UTC).isoformat()}
    repo.cards[c["id"]] = moved_away
    get_services().hub._on_card(card_event(moved_away, "UPDATE", old=c))

    await _wait_for(lambda: _card_texts(user, "IS") == ["a", "b"])
    assert _states(user, b["id"]) == (True, False)
    assert _states(user, c["id"]) == (False, False)  # alone in DOES


async def test_failed_reorder_puts_the_card_back_and_shows_the_message(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    repo.fail_next_update_codes = ["XX000"]
    await user.open(PATH_A)
    user.notify = notifications = _TypedNotify()

    _reorder(user, c["id"], "up")

    await user.should_see("Could not move the card. Please try again.")
    assert ("Could not move the card. Please try again.", "negative") in notifications.typed
    await _wait_for(lambda: _card_texts(user, "IS") == ["a", "b", "c"])
    assert repo.cards[c["id"]]["order_index"] == 3072.0
    assert _states(user, c["id"]) == (True, False)


async def test_two_move_clicks_before_the_write_returns_write_once(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    a, b, c = _three_cards(repo)
    await user.open(PATH_A)
    repo.update_gate = asyncio.Event()

    _reorder(user, c["id"], "up")
    _reorder(user, c["id"], "up")  # both clicks land before either handler task has run
    await _wait_for(lambda: repo.update_calls >= 1)
    await asyncio.sleep(0.1)

    assert repo.update_calls == 1
    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[c["id"]]["order_index"] == 1536.0)
    await asyncio.sleep(0.1)
    assert repo.update_calls == 1
    assert _card_texts(user, "IS") == ["a", "c", "b"]


async def test_reordering_never_adds_edited_keeps_the_author_and_needs_no_name(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "a", order_index=1024.0)
    b = seed_card(repo, SEEDED_ID_A, "IS", "b", author="Bea", order_index=2048.0)
    await user.open(PATH_A)
    await user.should_see(marker="name-banner")

    _reorder(user, b["id"], "up")

    await _wait_for(lambda: repo.cards[b["id"]]["order_index"] == 0.0)
    await asyncio.sleep(0.1)
    assert "(edited)" not in _meta(user, b["id"])
    assert _meta(user, b["id"]).startswith("Bea")
    assert repo.cards[b["id"]]["author"] == "Bea"
    assert repo.cards[b["id"]]["text_updated_at"] is None
    await user.should_not_see(DIALOG_TITLE)
    await user.should_see(marker="name-banner")
    assert _card_texts(user, "IS") == ["b", "a"]


def test_user_facing_message_is_pinned():
    assert cv.MOVE_FAILED == "Could not move the card. Please try again."
