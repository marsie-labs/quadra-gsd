"""Display-name rules (D-03, D-04): trim, 1-40 code points, fixed once stored, duplicates allowed."""

import pytest

from app.ui.identity import current_name, save_display_name, validate_display_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   ", None),
        (None, None),
        ("  Ann  ", "Ann"),
        ("a" * 40, "a" * 40),
        ("a" * 41, None),
        ("é" * 40, "é" * 40),
        ("é" * 41, None),
        ("Zoë 🙂", "Zoë 🙂"),
        ("  " + "a" * 40 + "  ", "a" * 40),
    ],
    ids=[
        "empty",
        "blank",
        "none",
        "trimmed",
        "40-ascii",
        "41-ascii",
        "40-multibyte",
        "41-multibyte",
        "unicode-and-emoji",
        "trim-before-count",
    ],
)
def test_validate_display_name(raw, expected):
    assert validate_display_name(raw) == expected


def test_save_trims_and_stores():
    storage: dict = {}
    assert save_display_name("  Ann  ", storage=storage) == "Ann"
    assert storage == {"display_name": "Ann"}


def test_save_blank_stores_nothing():
    storage: dict = {}
    assert save_display_name("   ", storage=storage) is None
    assert storage == {}


def test_save_never_overwrites_an_existing_name():
    """D-03: a stale banner or dialog in a second tab cannot rename the browser."""
    storage = {"display_name": "Ann"}
    assert save_display_name("Bob", storage=storage) == "Ann"
    assert storage == {"display_name": "Ann"}


def test_current_name_reads_validated_value():
    assert current_name(storage={}) is None
    assert current_name(storage={"display_name": "Ann"}) == "Ann"
    assert current_name(storage={"display_name": "   "}) is None
    assert current_name(storage={"display_name": "a" * 41}) is None


def test_two_browsers_may_share_a_name():
    first: dict = {}
    second: dict = {}
    assert save_display_name("Ann", storage=first) == "Ann"
    assert save_display_name("Ann", storage=second) == "Ann"
