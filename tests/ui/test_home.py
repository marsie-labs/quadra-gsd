"""Home page: inline project-name validation, Enter-to-submit, create-and-navigate."""

import asyncio

import pytest
from nicegui import ui

from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, install_fake_services

ERROR = "Required (max 100 characters)"


def _create_button(user) -> ui.button:
    (button,) = user.find(kind=ui.button, content="Create").elements
    return button


async def _settle() -> None:
    """Yield to the loop so scheduled handler tasks run up to their first real await (the gate)."""
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.mark.parametrize("text", ["", "   ", "a" * 101], ids=["empty", "blank", "101-chars"])
async def test_invalid_name_shows_inline_error_and_creates_nothing(user, text):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open("/")
    if text:
        user.find("Project name").clear().type(text)
    user.find("Create").click()
    await user.should_see(ERROR)
    assert repo.create_calls == 0
    await user.should_not_see(marker="quadrant-IS")


async def test_valid_name_creates_and_lands_on_canvas(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open("/")
    user.find("Project name").clear().type("Acme Widget")
    user.find("Create").click()
    await user.should_see(marker="project-name", content="Acme Widget", retries=50)
    await user.should_see(marker="quadrant-IS")
    assert repo.create_calls == 1


async def test_enter_key_creates_and_navigates(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open("/")
    field = user.find("Project name").clear().type("Enter Project")
    field.trigger("keydown.enter")
    await user.should_see(marker="project-name", content="Enter Project", retries=50)
    assert repo.create_calls == 1


async def test_double_enter_while_in_flight_creates_one_session(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    repo.create_gate = asyncio.Event()
    await user.open("/")
    field = user.find("Project name").clear().type("Twice Enter")
    field.trigger("keydown.enter")
    field.trigger("keydown.enter")
    await _settle()
    assert repo.create_calls == 1
    assert not _create_button(user).enabled
    repo.create_gate.set()
    await user.should_see(marker="project-name", content="Twice Enter", retries=50)
    assert repo.create_calls == 1
    assert len(repo.rows) == 2


async def test_double_click_while_in_flight_creates_one_session(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    repo.create_gate = asyncio.Event()
    await user.open("/")
    user.find("Project name").clear().type("Twice Click")
    # Two synchronous clicks: both pass UserInteraction's enabled check before the first
    # handler task runs, which is the same race a real double click produces.
    user.find("Create").click()
    user.find("Create").click()
    await _settle()
    assert repo.create_calls == 1
    assert not _create_button(user).enabled
    repo.create_gate.set()
    await user.should_see(marker="project-name", content="Twice Click", retries=50)
    assert repo.create_calls == 1
    assert len(repo.rows) == 2
