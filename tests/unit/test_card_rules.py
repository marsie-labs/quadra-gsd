"""Card text and author rules (CARD-01, IDEN-03) and the pure ordering/time helpers."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.deps import get_services
from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, install_fake_services


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        (" \t\n ", None),
        ("a", "a"),
        ("  x  ", "x"),
        ("a" * 500, "a" * 500),
        ("é" * 500, "é" * 500),
        ("a" * 501, None),
        ("é" * 501, None),
        ("  " + "a" * 500 + "  ", "a" * 500),
    ],
    ids=[
        "none",
        "empty",
        "spaces",
        "whitespace-mix",
        "single",
        "trimmed",
        "500",
        "500-multibyte",
        "501",
        "501-multibyte",
        "500-after-trim",
    ],
)
def test_validate_card_text(raw, expected):
    from app.services.sessions import validate_card_text

    assert validate_card_text(raw) == expected


def test_card_rule_constants():
    from app.services.sessions import CARD_TEXT_ERROR, MAX_AUTHOR, MAX_CARD_TEXT

    assert MAX_CARD_TEXT == 500
    assert MAX_AUTHOR == 40
    assert CARD_TEXT_ERROR == "Card text is required (max 500 characters)"


def test_next_order_index_steps_by_the_gap():
    from app.services.sessions import next_order_index

    assert next_order_index(None) == 1024.0
    assert next_order_index(2048.0) == 3072.0


def test_card_time_formats_use_the_given_zone():
    from app.ui.canvas_view import format_card_time, format_card_timestamp

    moment = datetime(2026, 10, 22, 13, 5, tzinfo=UTC)
    rome = ZoneInfo("Europe/Rome")

    assert format_card_time(moment, rome) == "15:05"
    assert "2026-10-22 15:05:00" in format_card_timestamp(moment, rome)


async def _ids() -> tuple[str, str]:
    view = await get_services().sessions.get(SEEDED_ID_A)
    assert view is not None
    return view.workspace_id, view.quadrants[0].id


async def test_add_card_rejects_blank_text_before_any_write():
    from app.services.sessions import InvalidCardText

    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    workspace_id, quadrant_id = await _ids()

    with pytest.raises(InvalidCardText):
        await get_services().sessions.add_card(workspace_id, quadrant_id, "   ", "Ann")

    assert repo.insert_calls == 0


async def test_add_card_rejects_oversized_text_before_any_write():
    from app.services.sessions import InvalidCardText

    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    workspace_id, quadrant_id = await _ids()

    with pytest.raises(InvalidCardText):
        await get_services().sessions.add_card(workspace_id, quadrant_id, "a" * 501, "Ann")

    assert repo.insert_calls == 0


@pytest.mark.parametrize("author", ["   ", "", "a" * 41], ids=["spaces", "empty", "41"])
async def test_add_card_rejects_invalid_author_before_any_write(author):
    from app.services.sessions import InvalidCardAuthor

    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    workspace_id, quadrant_id = await _ids()

    with pytest.raises(InvalidCardAuthor):
        await get_services().sessions.add_card(workspace_id, quadrant_id, "Idea", author)

    assert repo.insert_calls == 0


async def test_add_card_stores_trimmed_text_and_author():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    workspace_id, quadrant_id = await _ids()

    card = await get_services().sessions.add_card(
        workspace_id, quadrant_id, "  " + "é" * 500 + "  ", " Zoë 🙂 "
    )

    assert card.text == "é" * 500
    assert card.author == "Zoë 🙂"
    assert repo.insert_calls == 1
