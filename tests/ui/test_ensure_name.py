"""D-02: ensure_display_name() is the reusable authoring gate Phase 2 calls before card writes."""

from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, install_fake_services

ERROR = "Name is required (max 40 characters)"
ACTION = "/_test/author-action"


async def _open_dialog(user) -> None:
    await user.open(ACTION)
    user.find("Add card").click()
    await user.should_see("Enter your name to continue")


async def test_no_stored_name_opens_dialog_and_completes_after_valid_name(user):
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await _open_dialog(user)

    user.find("Continue").click()
    await user.should_see(ERROR)
    await user.should_see("Enter your name to continue")

    user.find("Your name").clear().type("   ")
    user.find("Continue").click()
    await user.should_see(ERROR)
    await user.should_see("Enter your name to continue")

    user.find("Your name").clear().type("Bob")
    user.find("Continue").click()
    await user.should_see(marker="result", content="authored by Bob")
    await user.should_not_see("Enter your name to continue")
    await user.should_not_see("Anonymous")


async def test_second_call_returns_immediately_without_dialog(user):
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await _open_dialog(user)
    user.find("Your name").clear().type("Bob")
    user.find("Continue").click()
    await user.should_see(marker="result", content="authored by Bob")

    user.find("Add card").click()
    await user.should_see(marker="result", content="authored by Bob")
    await user.should_not_see("Enter your name to continue")


async def test_cancel_aborts_stores_nothing_and_banner_still_shows(user):
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await _open_dialog(user)

    user.find("Cancel").click()
    await user.should_see(marker="result", content="cancelled")
    await user.should_not_see("Anonymous")

    await user.open(f"/s/{SEEDED_ID_A}")
    await user.should_see(marker="name-banner")
    await user.should_see(marker="display-name")


async def test_name_saved_on_canvas_banner_skips_the_dialog(user):
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(f"/s/{SEEDED_ID_A}")
    user.find(marker="name-input").clear().type("Ann")
    user.find("Save").click()
    await user.should_see(marker="display-name", content="Ann")

    await user.open(ACTION)
    user.find("Add card").click()
    await user.should_see(marker="result", content="authored by Ann")
    await user.should_not_see("Enter your name to continue")
