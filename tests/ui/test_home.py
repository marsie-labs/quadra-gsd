"""Home page: inline project-name validation, Enter-to-submit, create-and-navigate."""

import pytest

from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, install_fake_services

ERROR = "Required (max 100 characters)"


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
