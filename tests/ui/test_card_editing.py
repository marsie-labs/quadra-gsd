"""Card editing at its edges: validation, rollback, a card deleted meanwhile, in-place confirmation.

NiceGUI's test plugin runs a handler under the storage of the most recently opened request; every
UI test here uses a single browser. Offline: the REAL SessionService and CanvasView run over the
in-memory ``FakeRepository``, whose ``_touch`` mirrors the ``cards_touch`` trigger.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from nicegui import events, ui
from nicegui.testing.user_notify import UserNotify
from postgrest.exceptions import APIError

from app.deps import get_services
from app.models import CardView
from app.services.sessions import CARD_TEXT_ERROR, CardGone, InvalidCardText
from app.ui.canvas_view import CARD_GONE, EDIT_FAILED, card_meta_text
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
ENTER = "keydown.enter.exact.prevent"


def test_user_facing_messages_are_pinned():
    assert EDIT_FAILED == "Could not save the card. Please try again."
    assert CARD_GONE == "This card was deleted."
    assert CARD_TEXT_ERROR == "Card text is required (max 500 characters)"


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


def _card_element(browser, card_id: str) -> ui.card:
    """The ui.card of one card, for identity checks."""
    return next(iter(browser.find(marker=f"card-{card_id}").elements))


def _card_count(browser) -> int:
    """Card elements shown in all four quadrants (``find`` raises when there are none)."""
    columns = [
        next(iter(browser.find(marker=f"cards-{kind}").elements))
        for kind in ("IS", "IS_NOT", "DOES", "DOES_NOT")
    ]
    return sum(len(column.default_slot.children) for column in columns)


async def _wait_for(predicate, retries: int = 100) -> None:
    """Let the event loop run until ``predicate()`` holds. ``should_see`` would also match the
    textarea's own value, so it cannot tell a saved edit from a typed one."""
    for _ in range(retries):
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


def _meta(browser, card_id: str) -> str:
    with browser.scope(marker=f"card-{card_id}"):
        return next(iter(browser.find(marker="card-meta").elements)).text


def _open_editor(browser, card_id: str) -> None:
    with browser.scope(marker=f"card-{card_id}"):
        browser.find(marker="card-text").click()


def _editor(browser) -> ui.textarea:
    return next(iter(browser.find(marker="card-editor").elements))


def _type_and_enter(browser, text: str) -> None:
    browser.find(marker="card-editor").clear().type(text)
    browser.find(marker="card-editor").trigger(ENTER)


class _TypedNotify(UserNotify):
    """The simulated user's notify, also remembering each message's notification type."""

    def __init__(self) -> None:
        super().__init__()
        self.typed: list[tuple[str, str | None]] = []

    def __call__(self, message: str, **kwargs) -> None:
        self.typed.append((message, kwargs.get("type")))
        super().__call__(message, **kwargs)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


# ---------------------------------------------------------------- the fake mirrors the trigger


async def test_fake_update_stamps_updated_at_and_text_updated_at():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "before")

    updated = await repo.update_card_text(
        workspace_id=row["workspace_id"], card_id=row["id"], text="after"
    )

    assert updated is not None
    assert updated["text"] == "after"
    assert datetime.fromisoformat(updated["updated_at"]) > datetime.fromisoformat(row["updated_at"])
    assert updated["text_updated_at"] == updated["updated_at"]
    assert repo.update_calls == 1
    assert repo.cards[row["id"]]["text"] == "after"


async def test_fake_update_with_identical_text_keeps_text_updated_at():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "same")

    updated = await repo.update_card_text(
        workspace_id=row["workspace_id"], card_id=row["id"], text="same"
    )

    assert updated is not None
    assert datetime.fromisoformat(updated["updated_at"]) > datetime.fromisoformat(row["updated_at"])
    assert updated["text_updated_at"] is None


async def test_fake_update_scopes_to_workspace_and_live_cards():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    mine = seed_card(repo, SEEDED_ID_A, "IS", "mine")
    gone = seed_card(repo, SEEDED_ID_A, "IS", "gone")
    soft_delete_card(repo, gone["id"])
    other_workspace = repo.rows[SEEDED_ID_B]["id"]

    assert (
        await repo.update_card_text(workspace_id=mine["workspace_id"], card_id="no", text="x")
        is None
    )
    assert (
        await repo.update_card_text(workspace_id=other_workspace, card_id=mine["id"], text="x")
        is None
    )
    assert (
        await repo.update_card_text(workspace_id=gone["workspace_id"], card_id=gone["id"], text="x")
        is None
    )
    assert repo.cards[mine["id"]]["text"] == "mine"
    assert repo.cards[gone["id"]]["text"] == "gone"


async def test_fake_update_failure_code_and_gate():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "before")
    repo.fail_next_update_codes = ["XX000"]

    with pytest.raises(APIError) as failed:
        await repo.update_card_text(workspace_id=row["workspace_id"], card_id=row["id"], text="x")
    assert failed.value.code == "XX000"
    assert repo.cards[row["id"]]["text"] == "before"

    repo.update_gate = asyncio.Event()
    task = asyncio.create_task(
        repo.update_card_text(workspace_id=row["workspace_id"], card_id=row["id"], text="held")
    )
    await asyncio.sleep(0.05)
    assert repo.update_calls == 2  # counted before the gate
    assert repo.cards[row["id"]]["text"] == "before"
    repo.update_gate.set()
    updated = await task
    assert updated is not None
    assert updated["text"] == "held"

    with pytest.raises(APIError) as too_long:
        await repo.update_card_text(
            workspace_id=row["workspace_id"], card_id=row["id"], text="a" * 501
        )
    assert too_long.value.code == "23514"


# ---------------------------------------------------------------- edit_card on the fake


@pytest.mark.parametrize("text", ["", "   ", "é" * 501])
async def test_edit_card_rejects_invalid_text_before_any_write(text):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "before")

    with pytest.raises(InvalidCardText):
        await get_services().sessions.edit_card(row["workspace_id"], row["id"], text)

    assert repo.update_calls == 0
    assert repo.cards[row["id"]]["text"] == "before"


async def test_edit_card_trims_stores_500_code_points_and_keeps_author():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "before", author="Ann")
    sessions = get_services().sessions

    trimmed = await sessions.edit_card(row["workspace_id"], row["id"], "  New  ")
    assert trimmed.text == "New"
    assert trimmed.author == "Ann"
    assert trimmed.text_updated_at is not None

    long = await sessions.edit_card(row["workspace_id"], row["id"], "é" * 500)
    assert long.text == "é" * 500
    assert repo.cards[row["id"]]["author"] == "Ann"


async def test_edit_card_unknown_foreign_or_deleted_card_raises_card_gone():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    mine = seed_card(repo, SEEDED_ID_A, "IS", "mine")
    gone = seed_card(repo, SEEDED_ID_A, "IS", "gone")
    soft_delete_card(repo, gone["id"])
    foreign = repo.rows[SEEDED_ID_B]["id"]
    sessions = get_services().sessions

    with pytest.raises(CardGone):
        await sessions.edit_card(mine["workspace_id"], "00000000-0000-0000-0000-000000000000", "x")
    with pytest.raises(CardGone):
        await sessions.edit_card(foreign, mine["id"], "x")
    with pytest.raises(CardGone):
        await sessions.edit_card(gone["workspace_id"], gone["id"], "x")

    assert repo.cards[mine["id"]]["text"] == "mine"
    assert repo.cards[gone["id"]]["text"] == "gone"


# ---------------------------------------------------------------- the meta line


def test_card_meta_text_marks_edits_only_when_text_updated_at_is_set():
    tz = ZoneInfo("Europe/Rome")
    base = {
        "id": "c1",
        "workspace_id": "w1",
        "quadrant_id": "q1",
        "text": "t",
        "author": "Ann",
        "order_index": 1024.0,
        "created_at": datetime(2026, 10, 22, 13, 5, tzinfo=UTC),
        "updated_at": datetime(2026, 10, 22, 14, 0, tzinfo=UTC),
    }

    assert card_meta_text(CardView(**base), tz) == "Ann · 15:05"
    edited = CardView(**base, text_updated_at=datetime(2026, 10, 22, 14, 0, tzinfo=UTC))
    assert card_meta_text(edited, tz) == "Ann · 15:05 (edited)"


# ---------------------------------------------------------------- inline editing in the browser


async def test_enter_saves_new_text_with_edited_marker_and_keeps_author(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text", author="Ann")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    assert _editor(user).value == "old text"
    _type_and_enter(user, "new text")

    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "new text")
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == ["new text"]
    assert _meta(user, row["id"]).endswith("(edited)")
    assert repo.update_calls == 1
    assert repo.cards[row["id"]]["text"] == "new text"
    assert repo.cards[row["id"]]["author"] == "Ann"


async def test_own_edit_shows_before_the_write_returns_and_is_never_rebuilt(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)
    hub = get_services().hub
    element_before = _card_element(user, row["id"])
    repo.update_gate = asyncio.Event()

    _open_editor(user, row["id"])
    _type_and_enter(user, "new text")
    await _wait_for(lambda: repo.update_calls == 1)
    # The write is held: what is shown is the optimistic row.
    assert _card_texts(user, "IS") == ["new text"]
    assert repo.cards[row["id"]]["text"] == "old text"
    assert _meta(user, row["id"]).endswith("(edited)")

    # A stale echo (older updated_at, old text) changes nothing on screen.
    stale = {
        **row,
        "updated_at": _iso(datetime.fromisoformat(row["updated_at"]) - timedelta(seconds=1)),
    }
    hub._on_card(card_event(stale, "UPDATE", old=row))
    assert _card_texts(user, "IS") == ["new text"]
    assert _meta(user, row["id"]).endswith("(edited)")

    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "new text")
    await asyncio.sleep(0.1)  # let the confirmed row reach the page

    confirmed = dict(repo.cards[row["id"]])
    hub._on_card(card_event(confirmed, "UPDATE", old=row))  # the Realtime echo of our own write

    assert _card_count(user) == 1
    assert _card_texts(user, "IS") == ["new text"]
    assert _card_element(user, row["id"]) is element_before
    assert _meta(user, row["id"]).endswith("(edited)")


async def test_failed_edit_rolls_back_with_a_message_and_stays_editable(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    repo.fail_next_update_codes = ["XX000"]
    await user.open(PATH_A)
    user.notify = notifications = _TypedNotify()

    _open_editor(user, row["id"])
    _type_and_enter(user, "new text")

    await user.should_see(EDIT_FAILED)
    assert (EDIT_FAILED, "negative") in notifications.typed
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == ["old text"]
    assert "(edited)" not in _meta(user, row["id"])
    assert _card_count(user) == 1

    _open_editor(user, row["id"])
    _type_and_enter(user, "second try")
    await _wait_for(lambda: repo.update_calls == 2)
    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "second try")
    assert repo.update_calls == 2
    assert repo.cards[row["id"]]["text"] == "second try"


@pytest.mark.parametrize("bad", ["   ", "é" * 501])
async def test_invalid_edit_keeps_editor_open_and_writes_nothing(user, bad):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    _type_and_enter(user, bad)
    await asyncio.sleep(0.1)

    assert len(user.find(marker="card-editor").elements) == 1
    assert _editor(user).error == CARD_TEXT_ERROR
    assert repo.update_calls == 0
    assert _card_texts(user, "IS") == ["old text"]


async def test_edit_of_500_code_points_saves(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    _type_and_enter(user, "é" * 500)

    await _wait_for(lambda: repo.update_calls == 1)
    assert repo.cards[row["id"]]["text"] == "é" * 500
    await user.should_not_see(marker="card-editor")


async def test_edit_of_a_card_deleted_meanwhile_drops_it_with_a_warning(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed")
    await user.open(PATH_A)
    user.notify = notifications = _TypedNotify()

    _open_editor(user, row["id"])
    soft_delete_card(repo, row["id"])  # deleted elsewhere, no event reached this page
    _type_and_enter(user, "too late")

    await _wait_for(lambda: repo.update_calls == 1)
    await user.should_see(CARD_GONE)
    assert repo.cards[row["id"]]["text"] == "doomed"
    assert _card_count(user) == 0
    assert (CARD_GONE, "warning") in notifications.typed
    with user.scope(marker="quadrant-IS"):
        await user.should_see("No cards yet")


async def test_marker_follows_text_updated_at_not_other_changes(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "plain")
    await user.open(PATH_A)
    hub = get_services().hub
    does_id = next(q["id"] for q in repo.rows[SEEDED_ID_A]["quadrants"] if q["kind"] == "DOES")

    assert "(edited)" not in _meta(user, row["id"])

    moved = {**row, "quadrant_id": does_id, "order_index": 5000.0}
    hub._on_card(card_event(moved, "UPDATE", old=row))
    assert _card_texts(user, "DOES") == ["plain"]
    assert "(edited)" not in _meta(user, row["id"])

    stamp = datetime.fromisoformat(row["updated_at"]) + timedelta(seconds=5)
    edited = {**moved, "text": "changed", "updated_at": _iso(stamp), "text_updated_at": _iso(stamp)}
    hub._on_card(card_event(edited, "UPDATE", old=moved))
    assert _card_texts(user, "DOES") == ["changed"]
    assert _meta(user, row["id"]).endswith("(edited)")


async def test_reopened_canvas_shows_the_marker_for_an_edited_card(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    stamp = _iso(datetime.now(UTC))
    edited = seed_card(repo, SEEDED_ID_A, "IS", "was edited", text_updated_at=stamp)
    plain = seed_card(repo, SEEDED_ID_A, "IS", "never edited", order_index=2048.0)
    await user.open(PATH_A)

    assert _meta(user, edited["id"]).endswith("(edited)")
    assert "(edited)" not in _meta(user, plain["id"])


async def test_editing_by_id_leaves_a_card_with_identical_text_alone(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    first = seed_card(repo, SEEDED_ID_A, "IS", "same", order_index=1024.0)
    second = seed_card(repo, SEEDED_ID_A, "IS", "same", order_index=2048.0)
    await user.open(PATH_A)
    hub = get_services().hub

    _open_editor(user, second["id"])
    _type_and_enter(user, "changed")
    await _wait_for(lambda: repo.cards[second["id"]]["text"] == "changed")
    await asyncio.sleep(0.1)  # let the confirmed row reach the page
    hub._on_card(card_event(dict(repo.cards[second["id"]]), "UPDATE", old=second))

    assert _card_texts(user, "IS") == ["same", "changed"]
    assert _card_count(user) == 2
    assert "(edited)" not in _meta(user, first["id"])
    assert _meta(user, second["id"]).endswith("(edited)")


async def test_edited_markup_is_shown_literally(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    _type_and_enter(user, "<b>x</b>")

    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "<b>x</b>")
    await user.should_not_see(marker="card-editor")
    with user.scope(marker=f"card-{row['id']}"):
        text = next(iter(user.find(marker="card-text").elements))
    assert isinstance(text, ui.label)
    assert text.text == "<b>x</b>"
    assert repo.cards[row["id"]]["text"] == "<b>x</b>"


# ---------------------------------------------------------------- the card menu and editor rules

DIALOG_TITLE = "Enter your name to continue"


def _menu_button(browser, card_id: str) -> ui.button:
    with browser.scope(marker=f"card-{card_id}"):
        return next(iter(browser.find(marker="card-menu").elements))


def _menu_edit(browser, card_id: str) -> None:
    """Choose Edit in the card's menu (menu items are found while the menu is closed)."""
    with browser.scope(marker=f"card-{card_id}"):
        browser.find(marker="card-action-edit").click()


def _listener_handlers(element: ui.element, event_type: str) -> list:
    return [
        listener.handler
        for listener in element._event_listeners.values()
        if listener.type == event_type
    ]


def _fire(browser, element: ui.element, handler) -> None:
    """Run a captured listener handler, as an event that was already queued would."""
    with browser.client:
        events.handle_event(
            handler, events.GenericEventArguments(sender=element, client=browser.client, args={})
        )


async def test_every_card_has_one_enabled_menu_button_with_a_distinct_accessible_name(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    first = seed_card(repo, SEEDED_ID_A, "IS", "alpha", order_index=1024.0)
    second = seed_card(repo, SEEDED_ID_A, "IS", "beta", order_index=2048.0)
    long_text = "x" * 60
    third = seed_card(repo, SEEDED_ID_A, "DOES", long_text)
    await user.open(PATH_A)

    assert len(user.find(marker="card-menu").elements) == 3
    for card_id in (first["id"], second["id"], third["id"]):
        with user.scope(marker=f"card-{card_id}"):
            assert len(user.find(marker="card-menu").elements) == 1
        assert _menu_button(user, card_id).enabled
        assert _menu_button(user, card_id).props["icon"] == "more_vert"
    assert _menu_button(user, first["id"]).props["aria-label"] == "Card actions: alpha"
    assert _menu_button(user, second["id"]).props["aria-label"] == "Card actions: beta"
    assert _menu_button(user, third["id"]).props["aria-label"] == "Card actions: " + "x" * 40

    _open_editor(user, first["id"])
    _type_and_enter(user, "alpha edited")
    await _wait_for(lambda: repo.cards[first["id"]]["text"] == "alpha edited")
    await _wait_for(
        lambda: _menu_button(user, first["id"]).props["aria-label"] == "Card actions: alpha edited"
    )


async def test_menu_edit_item_opens_the_editor_with_the_card_text(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _menu_edit(user, row["id"])

    assert _editor(user).value == "old text"
    assert not _card_element(user, row["id"]).default_slot.children[0].visible


async def test_editor_registers_one_exact_enter_listener_plus_esc_and_blur(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    types = [listener.type for listener in _editor(user)._event_listeners.values()]

    assert [t for t in types if t.startswith("keydown.enter")] == [ENTER]
    assert "keydown.enter" not in types
    assert "keydown.esc" in types
    assert "blur" in types


async def test_multi_line_text_is_stored_with_its_line_break_and_shown_on_two_lines(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    _type_and_enter(user, "line one\nline two")

    await _wait_for(lambda: repo.update_calls == 1)
    assert repo.cards[row["id"]]["text"] == "line one\nline two"
    await user.should_not_see(marker="card-editor")
    with user.scope(marker=f"card-{row['id']}"):
        text = next(iter(user.find(marker="card-text").elements))
    assert text.text == "line one\nline two"
    assert "whitespace-pre-wrap" in text.classes


async def test_blur_saves_changed_text(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    user.find(marker="card-editor").clear().type("clicked away")
    user.find(marker="card-editor").trigger("blur")

    await _wait_for(lambda: repo.update_calls == 1)
    await _wait_for(lambda: _card_texts(user, "IS") == ["clicked away"])
    assert repo.cards[row["id"]]["text"] == "clicked away"
    await user.should_not_see(marker="card-editor")


async def test_enter_then_a_queued_blur_writes_once(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    editor = _editor(user)
    (blur,) = _listener_handlers(editor, "blur")
    _type_and_enter(user, "new text")
    await _wait_for(lambda: repo.update_calls == 1)
    await user.should_not_see(marker="card-editor")

    _fire(user, editor, blur)  # the blur that was already queued behind Enter
    await asyncio.sleep(0.1)

    assert repo.update_calls == 1
    assert repo.cards[row["id"]]["text"] == "new text"


async def test_esc_then_a_queued_blur_writes_nothing(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    editor = _editor(user)
    (blur,) = _listener_handlers(editor, "blur")
    user.find(marker="card-editor").clear().type("never saved")
    user.find(marker="card-editor").trigger("keydown.esc")
    await user.should_not_see(marker="card-editor")

    _fire(user, editor, blur)
    await asyncio.sleep(0.1)

    assert repo.update_calls == 0
    assert _card_texts(user, "IS") == ["old text"]


async def test_esc_closes_the_editor_and_shows_the_original_text(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    user.find(marker="card-editor").clear().type("typed then dropped")
    user.find(marker="card-editor").trigger("keydown.esc")

    await user.should_not_see(marker="card-editor")
    with user.scope(marker=f"card-{row['id']}"):
        text = next(iter(user.find(marker="card-text").elements))
    assert text.visible
    assert text.text == "old text"
    assert repo.update_calls == 0
    assert "(edited)" not in _meta(user, row["id"])


async def test_unchanged_text_padded_with_spaces_writes_nothing_and_closes_the_editor(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    _type_and_enter(user, "  old text  ")
    await user.should_not_see(marker="card-editor")
    await asyncio.sleep(0.1)

    assert repo.update_calls == 0
    assert _card_texts(user, "IS") == ["old text"]
    assert "(edited)" not in _meta(user, row["id"])


async def test_blur_with_empty_text_keeps_the_editor_open_with_the_error_until_esc(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)

    _open_editor(user, row["id"])
    user.find(marker="card-editor").clear()
    user.find(marker="card-editor").trigger("blur")
    await asyncio.sleep(0.1)

    assert len(user.find(marker="card-editor").elements) == 1
    assert _editor(user).error == CARD_TEXT_ERROR
    assert repo.update_calls == 0

    user.find(marker="card-editor").trigger("keydown.esc")
    await user.should_not_see(marker="card-editor")
    assert _card_texts(user, "IS") == ["old text"]
    assert repo.update_calls == 0


async def test_double_enter_in_flight_writes_once_and_guards_the_card(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    await user.open(PATH_A)
    repo.update_gate = asyncio.Event()

    _open_editor(user, row["id"])
    user.find(marker="card-editor").clear().type("new text")
    user.find(marker="card-editor").trigger(ENTER)
    user.find(marker="card-editor").trigger(ENTER)
    await _wait_for(lambda: repo.update_calls == 1)
    await asyncio.sleep(0.1)

    assert repo.update_calls == 1
    assert not _menu_button(user, row["id"]).enabled
    _open_editor(user, row["id"])  # clicking the text while the write is in flight
    await user.should_not_see(marker="card-editor")

    repo.update_gate.set()
    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "new text")
    await _wait_for(lambda: _menu_button(user, row["id"]).enabled)
    assert repo.update_calls == 1


async def test_anyone_edits_without_a_name_and_the_author_stays(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text", author="Ann")
    await user.open(PATH_A)
    await user.should_see(marker="name-banner")

    _menu_edit(user, row["id"])
    _type_and_enter(user, "edited by a stranger")

    await _wait_for(lambda: repo.cards[row["id"]]["text"] == "edited by a stranger")
    await user.should_not_see(DIALOG_TITLE)
    await user.should_see(marker="name-banner")
    assert repo.cards[row["id"]]["author"] == "Ann"
    assert repo.update_calls == 1
