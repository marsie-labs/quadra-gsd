"""Card editing at its edges: validation, rollback, a card deleted meanwhile, in-place confirmation.

NiceGUI's test plugin runs a handler under the storage of the most recently opened request; every
UI test here uses a single browser. Offline: the REAL SessionService and CanvasView run over the
in-memory ``FakeRepository``, whose ``_touch`` mirrors the ``cards_touch`` trigger.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from nicegui import ui
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


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


def _card_element(browser, card_id: str) -> ui.card:
    """The ui.card of one card, for identity checks."""
    return next(iter(browser.find(marker=f"card-{card_id}").elements))


def _card_count(browser) -> int:
    return len(browser.find(marker="card").elements)


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

    with user.scope(marker="cards-IS"):
        await user.should_see("new text", retries=50)
    await user.should_not_see(marker="card-editor")
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
    with user.scope(marker="cards-IS"):
        await user.should_see("new text", retries=50)
    # The write is held: what is shown is the optimistic row.
    assert repo.update_calls == 1
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
    with user.scope(marker="cards-IS"):
        await user.should_see("new text", retries=50)
    for _ in range(50):
        if repo.cards[row["id"]]["text"] == "new text":
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)

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

    _open_editor(user, row["id"])
    _type_and_enter(user, "new text")

    await user.should_see(EDIT_FAILED)
    assert _card_texts(user, "IS") == ["old text"]
    assert "(edited)" not in _meta(user, row["id"])
    assert _card_count(user) == 1

    _open_editor(user, row["id"])
    _type_and_enter(user, "second try")
    with user.scope(marker="cards-IS"):
        await user.should_see("second try", retries=50)
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

    for _ in range(50):
        if repo.update_calls:
            break
        await asyncio.sleep(0.02)
    assert repo.update_calls == 1
    assert repo.cards[row["id"]]["text"] == "é" * 500
    await user.should_not_see(marker="card-editor")


async def test_edit_of_a_card_deleted_meanwhile_drops_it_with_a_warning(user, monkeypatch):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed")
    await user.open(PATH_A)
    notifications: list[tuple[str, str | None]] = []
    original = ui.notify

    def record(message, **kwargs):
        notifications.append((message, kwargs.get("type")))
        return original(message, **kwargs)

    monkeypatch.setattr(ui, "notify", record)

    _open_editor(user, row["id"])
    soft_delete_card(repo, row["id"])  # deleted elsewhere, no event reached this page
    _type_and_enter(user, "too late")

    await user.should_see(CARD_GONE)
    assert _card_count(user) == 0
    assert (CARD_GONE, "warning") in notifications
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
    with user.scope(marker="cards-IS"):
        await user.should_see("changed", retries=50)
    for _ in range(50):
        if repo.cards[second["id"]]["text"] == "changed":
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)
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

    with user.scope(marker="cards-IS"):
        await user.should_see("<b>x</b>", retries=50)
    with user.scope(marker=f"card-{row['id']}"):
        text = next(iter(user.find(marker="card-text").elements))
    assert isinstance(text, ui.label)
    assert text.text == "<b>x</b>"
    assert repo.cards[row["id"]]["text"] == "<b>x</b>"
