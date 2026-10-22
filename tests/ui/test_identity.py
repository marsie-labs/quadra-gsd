"""IDEN-01/IDEN-02: inline name banner (D-01), per-browser memory, read-only header (D-03)."""

import pytest

from tests.ui.fakes import (
    SEEDED_ID_A,
    SEEDED_ID_B,
    SEEDED_NAME_A,
    SEEDED_NAME_B,
    install_fake_services,
)

ERROR = "Name is required (max 40 characters)"
PATH_A = f"/s/{SEEDED_ID_A}"
PATH_B = f"/s/{SEEDED_ID_B}"
QUADRANTS = ("IS", "IS_NOT", "DOES", "DOES_NOT")


def _seed() -> None:
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})


async def _save(user, text: str) -> None:
    field = user.find(marker="name-input").clear()
    if text:
        field.type(text)
    user.find("Save").click()


async def test_first_visit_shows_banner_over_a_fully_visible_canvas(user):
    _seed()
    await user.open(PATH_A)
    await user.should_see(marker="name-banner")
    await user.should_see(SEEDED_NAME_A)
    for kind in QUADRANTS:
        await user.should_see(marker=f"quadrant-{kind}")


async def test_no_stored_name_shows_empty_header_never_a_placeholder(user):
    _seed()
    await user.open(PATH_A)
    await user.should_see(marker="name-banner")
    await user.should_see(marker="display-name")
    await user.should_not_see(content="Anonymous")


@pytest.mark.parametrize("text", ["", "   ", "a" * 41], ids=["empty", "blank", "41-chars"])
async def test_invalid_name_shows_inline_error_and_keeps_banner(user, text):
    _seed()
    await user.open(PATH_A)
    await _save(user, text)
    await user.should_see(ERROR)
    await user.should_see(marker="name-banner")
    await user.should_see(marker="quadrant-IS")


async def test_valid_name_removes_banner_and_shows_in_header(user):
    _seed()
    await user.open(PATH_A)
    await _save(user, "  Ann  ")
    await user.should_see(marker="display-name", content="Ann")
    await user.should_not_see(marker="name-banner")


async def test_forty_multibyte_characters_are_accepted(user):
    _seed()
    await user.open(PATH_A)
    await _save(user, "é" * 40)
    await user.should_see(marker="display-name", content="é" * 40)
    await user.should_not_see(marker="name-banner")


async def test_name_persists_across_reload_and_other_sessions(user):
    _seed()
    await user.open(PATH_A)
    await _save(user, "Ann")
    await user.should_see(marker="display-name", content="Ann")

    await user.open(PATH_A)
    await user.should_not_see(marker="name-banner")
    await user.should_see(marker="display-name", content="Ann")

    await user.open(PATH_B)
    await user.should_see(SEEDED_NAME_B)
    await user.should_not_see(marker="name-banner")
    await user.should_see(marker="display-name", content="Ann")


async def test_unicode_name_round_trips_exactly(user):
    _seed()
    await user.open(PATH_A)
    await _save(user, "Zoë 🙂")
    await user.should_see(marker="display-name", content="Zoë 🙂")

    await user.open(PATH_A)
    await user.should_see(marker="display-name", content="Zoë 🙂")
    await user.should_not_see(marker="name-banner")


async def test_header_name_is_read_only_text(user):
    _seed()
    await user.open(PATH_A)
    await _save(user, "Ann")
    await user.should_see(marker="display-name", content="Ann")
    await user.should_not_see("Rename")
    await user.should_not_see("Change name")
    await user.should_not_see("Edit name")
    labels = user.find(marker="display-name")
    assert len(labels.elements) == 1
    (element,) = labels.elements
    assert type(element).__name__ == "Label"


async def test_second_browser_is_prompted_independently_and_may_pick_same_name(user, create_user):
    _seed()
    await user.open(PATH_A)
    await _save(user, "Ann")
    await user.should_see(marker="display-name", content="Ann")

    other = create_user()
    await other.open(PATH_A)
    await other.should_see(marker="name-banner")
    await other.should_see(marker="quadrant-IS")
    other.find(marker="name-input").clear().type("Ann")
    other.find("Save").click()
    await other.should_see(marker="display-name", content="Ann")
    await other.should_not_see(marker="name-banner")
