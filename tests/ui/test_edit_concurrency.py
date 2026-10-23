"""D-04: what other participants do to a card never destroys the editor someone has open on it.

A remote edit, a reconnect resync and a remote move keep the open textarea and its draft; a
remote delete closes it with a warning; and once a save settles, the row with the greater
``updated_at`` is the one every screen shows. Events are fed to ``hub._on_card`` exactly as the
Realtime socket loop would hand them over. NiceGUI's test plugin runs a handler under the storage
of the most recently opened request, so every test here uses a single browser.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from nicegui import ui
from nicegui.testing.user_notify import UserNotify

from app.deps import get_services
from app.ui.canvas_view import CARD_GONE
from tests.ui.fakes import (
    SEEDED_ID_A,
    SEEDED_NAME_A,
    FakeRepository,
    card_event,
    install_fake_services,
    seed_card,
)

PATH_A = f"/s/{SEEDED_ID_A}"
ENTER = "keydown.enter.exact.prevent"


class _TypedNotify(UserNotify):
    """The simulated user's notify, also remembering each message's notification type."""

    def __init__(self) -> None:
        super().__init__()
        self.typed: list[tuple[str, str | None]] = []

    def __call__(self, message: str, **kwargs) -> None:
        self.typed.append((message, kwargs.get("type")))
        super().__call__(message, **kwargs)


def _typed_notify(user) -> _TypedNotify:
    """Install a typed notify. The user fixture re-points ``ui.notify`` at its notifier on every
    attribute access, so one access (``user.client``) makes the swap effective right away."""
    notifications = _TypedNotify()
    user.notify = notifications
    assert user.client is not None
    return notifications


def _card_element(browser, card_id: str) -> ui.card:
    return next(iter(browser.find(marker=f"card-{card_id}").elements))


def _hidden_label_text(browser, card_id: str) -> str:
    """The card's first child: its text label, which is hidden while an editor is open."""
    return _card_element(browser, card_id).default_slot.children[0].text


def _card_texts(browser, kind: str) -> list[str]:
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


def _editor(browser) -> ui.textarea:
    return next(iter(browser.find(marker="card-editor").elements))


def _quadrant_id(repo: FakeRepository, kind: str) -> str:
    return next(q["id"] for q in repo.rows[SEEDED_ID_A]["quadrants"] if q["kind"] == kind)


def _remote_change(repo: FakeRepository, card_id: str, **changes: Any) -> dict[str, Any]:
    """Someone else's committed UPDATE: stored in the fake DB (stamped like the trigger) and
    returned as the row their Realtime event would carry."""
    repo.cards[card_id] = repo._touch(repo.cards[card_id], changes)
    return dict(repo.cards[card_id])


def _reconnect(user) -> None:
    for handler in list(user.client.connect_handlers):
        user.client.safe_invoke(handler)


async def _settle() -> None:
    """Wait until no canvas resync task is running (test-harness wait, not app polling)."""
    for _ in range(100):
        busy = [
            t
            for t in asyncio.all_tasks()
            if t.get_name().startswith("canvas resync") and not t.done()
        ]
        if not busy:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("a canvas resync never finished")


async def _wait_for(predicate, retries: int = 100) -> None:
    for _ in range(retries):
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


async def _draft_open(user, base: str = "base", draft: str = "mine"):
    """A canvas with one IS card whose editor is open and holds ``draft`` (nothing saved yet)."""
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", base)
    await user.open(PATH_A)
    with user.scope(marker=f"card-{row['id']}"):
        user.find(marker="card-text").click()
    user.find(marker="card-editor").clear().type(draft)
    return repo, row, _editor(user)


def test_the_mid_edit_delete_warning_text_is_pinned():
    assert CARD_GONE == "This card was deleted."


# ---------------------------------------------------------------- a remote edit meanwhile


async def test_remote_edit_keeps_the_same_editor_and_draft_and_updates_the_hidden_text(user):
    repo, row, editor = await _draft_open(user)

    get_services().hub._on_card(
        card_event(_remote_change(repo, row["id"], text="theirs"), "UPDATE", old=row)
    )

    assert _editor(user) is editor
    assert editor.value == "mine"
    assert editor in _card_element(user, row["id"]).default_slot.children
    assert _hidden_label_text(user, row["id"]) == "theirs"
    assert repo.update_calls == 0


async def test_enter_after_a_remote_edit_saves_the_draft_and_it_wins(user):
    repo, row, _ = await _draft_open(user)
    get_services().hub._on_card(
        card_event(_remote_change(repo, row["id"], text="theirs"), "UPDATE", old=row)
    )

    user.find(marker="card-editor").trigger(ENTER)

    await _wait_for(lambda: repo.update_calls == 1)
    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "mine")
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == ["mine"]
    assert repo.update_calls == 1


async def test_esc_after_a_remote_edit_shows_the_remote_text_and_writes_nothing(user):
    repo, row, _ = await _draft_open(user)
    get_services().hub._on_card(
        card_event(_remote_change(repo, row["id"], text="theirs"), "UPDATE", old=row)
    )

    user.find(marker="card-editor").trigger("keydown.esc")

    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == ["theirs"]
    assert repo.update_calls == 0


# ---------------------------------------------------------------- a resync meanwhile


async def test_resync_keeps_the_editor_and_draft_and_esc_shows_the_database_text(user):
    repo, row, editor = await _draft_open(user)
    repo.cards[row["id"]]["text"] = "from db"

    _reconnect(user)
    await _settle()

    assert _editor(user) is editor
    assert editor.value == "mine"
    assert _hidden_label_text(user, row["id"]) == "from db"

    user.find(marker="card-editor").trigger("keydown.esc")
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == ["from db"]
    assert repo.update_calls == 0


# ---------------------------------------------------------------- a remote move meanwhile


async def test_remote_move_keeps_the_editor_and_draft_in_the_new_column_and_enter_saves(user):
    repo, row, editor = await _draft_open(user)
    does_id = _quadrant_id(repo, "DOES")

    get_services().hub._on_card(
        card_event(
            _remote_change(repo, row["id"], quadrant_id=does_id, order_index=5000.0),
            "UPDATE",
            old=row,
        )
    )

    does_column = next(iter(user.find(marker="cards-DOES").elements))
    (card,) = does_column.default_slot.children
    assert card is _card_element(user, row["id"])
    assert _editor(user) is editor
    assert editor in card.default_slot.children
    assert editor.value == "mine"
    assert _card_texts(user, "IS") == []

    user.find(marker="card-editor").trigger(ENTER)
    await _wait_for(lambda: repo.update_calls == 1)
    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "mine")
    assert _card_texts(user, "DOES") == ["mine"]


# ---------------------------------------------------------------- a remote delete meanwhile


async def test_soft_delete_event_closes_the_editor_and_warns(user):
    repo, row, _ = await _draft_open(user)
    notifications = _typed_notify(user)

    get_services().hub._on_card(
        card_event(
            _remote_change(repo, row["id"], deleted_at="2999-01-01T00:00:00+00:00"),
            "UPDATE",
            old=row,
        )
    )

    await user.should_see(CARD_GONE)
    assert (CARD_GONE, "warning") in notifications.typed
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == []
    with user.scope(marker="quadrant-IS"):
        await user.should_see("No cards yet")
    assert repo.update_calls == 0


async def test_delete_event_with_only_the_id_closes_the_editor_and_warns(user):
    _, row, _ = await _draft_open(user)
    notifications = _typed_notify(user)

    get_services().hub._on_card(card_event({}, "DELETE", old={"id": row["id"]}))

    await user.should_see(CARD_GONE)
    assert (CARD_GONE, "warning") in notifications.typed
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == []


async def test_a_resync_without_the_card_closes_the_editor_and_warns(user):
    repo, row, _ = await _draft_open(user)
    repo.cards[row["id"]]["deleted_at"] = "2999-01-01T00:00:00+00:00"

    _reconnect(user)
    await _settle()

    await user.should_see(CARD_GONE)
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == []


async def test_deleting_a_card_nobody_is_editing_shows_no_warning(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "plain")
    await user.open(PATH_A)
    notifications = _typed_notify(user)

    get_services().hub._on_card(card_event({}, "DELETE", old={"id": row["id"]}))

    assert _card_texts(user, "IS") == []
    assert notifications.typed == []


# ---------------------------------------------------------------- last save wins


async def _save_held(user, repo, row) -> None:
    """Press Enter on the open draft with the write held in flight."""
    repo.update_gate = asyncio.Event()
    user.find(marker="card-editor").trigger(ENTER)
    await _wait_for(lambda: repo.update_calls == 1)
    await user.should_not_see(marker="card-editor")


async def test_stale_event_during_a_save_changes_nothing_on_screen(user):
    repo, row, _ = await _draft_open(user)
    await _save_held(user, repo, row)
    older = (datetime.fromisoformat(row["updated_at"]) - timedelta(seconds=1)).isoformat()

    get_services().hub._on_card(
        card_event({**row, "text": "stale", "updated_at": older}, "UPDATE", old=row)
    )

    assert _card_texts(user, "IS") == ["mine"]
    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "mine")
    await asyncio.sleep(0.1)
    assert _card_texts(user, "IS") == ["mine"]


async def test_a_remote_change_committed_after_the_save_wins_on_this_screen(user):
    repo, row, _ = await _draft_open(user)
    await _save_held(user, repo, row)
    future = (datetime.fromisoformat(row["updated_at"]) + timedelta(hours=1)).isoformat()

    get_services().hub._on_card(
        card_event({**row, "text": "later remote", "updated_at": future}, "UPDATE", old=row)
    )
    assert _card_texts(user, "IS") == ["mine"]  # while the save is in flight, nothing changes

    repo.update_gate.set()
    await _wait_for(lambda: _card_texts(user, "IS") == ["later remote"])


async def test_a_remote_change_committed_before_the_save_loses_to_it(user):
    repo, row, _ = await _draft_open(user)
    await _save_held(user, repo, row)
    barely = (datetime.fromisoformat(row["updated_at"]) + timedelta(microseconds=1)).isoformat()

    get_services().hub._on_card(
        card_event({**row, "text": "earlier remote", "updated_at": barely}, "UPDATE", old=row)
    )

    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "mine")
    await asyncio.sleep(0.1)
    assert _card_texts(user, "IS") == ["mine"]
