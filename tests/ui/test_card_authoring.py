"""Authoring edges: the name gate at add time, double submits, failed writes, banner idempotency.

NiceGUI's test plugin runs a click handler under the storage of the most recently opened
request; every test here uses a single browser.
"""

import asyncio
import logging

from nicegui import ui
from nicegui.testing.user_interaction import UserInteraction

from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, install_fake_services

PATH_A = f"/s/{SEEDED_ID_A}"
DIALOG_TITLE = "Enter your name to continue"
FAILURE = "Could not add the card. Please try again."


def _in_dialog(element: ui.element) -> bool:
    parent = element.parent_slot.parent if element.parent_slot else None
    while parent is not None:
        if isinstance(parent, ui.dialog):
            return True
        parent = parent.parent_slot.parent if parent.parent_slot else None
    return False


def _dialog_name_input(user) -> UserInteraction:
    """The name field inside the open dialog (the inline banner has a same-labelled field)."""
    inputs = [e for e in user.find(kind=ui.input).elements if _in_dialog(e)]
    assert len(inputs) == 1
    return UserInteraction(user, {inputs[0]}, None)


async def _save_name(user, name: str) -> None:
    user.find(marker="name-input").clear().type(name)
    user.find("Save").click()
    await user.should_see(marker="display-name", content=name)


def _field_value(user, kind: str) -> str:
    return next(iter(user.find(marker=f"add-input-{kind}").elements)).value


async def test_unnamed_add_cancel_writes_nothing(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)

    user.find(marker="add-input-IS").type("Idea")
    user.find(marker="add-button-IS").click()
    await user.should_see(DIALOG_TITLE)

    user.find("Cancel").click()
    await user.should_not_see(DIALOG_TITLE)
    assert repo.insert_calls == 0
    assert _field_value(user, "IS") == "Idea"
    await user.should_see(marker="name-banner")
    await user.should_not_see("Anonymous")


async def test_unnamed_add_continue_authors_card(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)

    user.find(marker="add-input-IS").type("Idea")
    user.find(marker="add-button-IS").click()
    await user.should_see(DIALOG_TITLE)
    _dialog_name_input(user).clear().type("Bob")
    user.find("Continue").click()

    with user.scope(marker="cards-IS"):
        await user.should_see("Idea", retries=50)
    await user.should_see(marker="card-meta", content="Bob · ")
    await user.should_see(marker="display-name", content="Bob")
    await user.should_not_see(marker="name-banner")
    assert [c["author"] for c in repo.cards.values()] == ["Bob"]

    user.find(marker="add-input-DOES").type("Second")
    user.find(marker="add-button-DOES").click()
    with user.scope(marker="cards-DOES"):
        await user.should_see("Second", retries=50)
    await user.should_not_see(DIALOG_TITLE)
    assert repo.insert_calls == 2


async def test_double_submit_creates_one_card(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    repo.insert_gate = asyncio.Event()
    await user.open(PATH_A)
    await _save_name(user, "Ann")

    user.find(marker="add-input-IS").type("Once")
    user.find(marker="add-button-IS").click()
    user.find(marker="add-button-IS").click()
    user.find(marker="add-input-IS").trigger("keydown.enter")
    await asyncio.sleep(0.2)
    repo.insert_gate.set()

    with user.scope(marker="cards-IS"):
        await user.should_see("Once", retries=50)
    assert repo.insert_calls == 1
    assert len(user.find(marker="card").elements) == 1


async def test_failed_write_keeps_text_and_releases(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    repo.fail_next_insert_codes = ["XX000"]
    await user.open(PATH_A)
    await _save_name(user, "Ann")

    user.find(marker="add-input-IS").type("Retry me")
    user.find(marker="add-button-IS").click()
    await user.should_see(FAILURE)
    assert _field_value(user, "IS") == "Retry me"
    assert not repo.cards

    user.find(marker="add-button-IS").click()
    with user.scope(marker="cards-IS"):
        await user.should_see("Retry me", retries=50)
    assert repo.insert_calls == 2


async def test_banner_double_enter_is_harmless(user, caplog):
    """Two queued Enter events for one banner (WR-06): the second must not touch a deleted element.

    The first handler deletes the banner and clears its listeners, so a second ``trigger`` would
    find none; the stale handler reference is called twice to reproduce two events already queued.
    """
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)

    name_input = next(iter(user.find(marker="name-input").elements))
    handlers = [
        listener.handler
        for listener in name_input._event_listeners.values()
        if listener.type == "keydown.enter"
    ]
    assert len(handlers) == 1
    name_input.value = "Ann"

    with caplog.at_level(logging.ERROR), user.client:
        handlers[0]()
        handlers[0]()

    await user.should_see(marker="display-name", content="Ann")
    await user.should_not_see(marker="name-banner")
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
