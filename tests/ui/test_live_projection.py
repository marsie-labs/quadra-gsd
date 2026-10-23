"""The canvas as a live projection of the cards table: edits, moves, deletes, foreign events.

Events are fed to ``hub._on_card`` exactly as the Realtime socket loop would hand them over; the
rows come from ``seed_card`` so the fake repository and the canvases agree on ids and workspaces.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.deps import get_services
from tests.ui.fakes import (
    SEEDED_ID_A,
    SEEDED_ID_B,
    SEEDED_NAME_A,
    SEEDED_NAME_B,
    FakeRepository,
    card_event,
    install_fake_services,
    seed_card,
)

PATH_A = f"/s/{SEEDED_ID_A}"
PATH_B = f"/s/{SEEDED_ID_B}"
EMPTY = "No cards yet"


def _card_texts(browser, kind: str) -> list[str]:
    """Texts of the card widgets inside a quadrant's card column, in child order."""
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


def _quadrant_id(repo: FakeRepository, session_id: str, kind: str) -> str:
    return next(q["id"] for q in repo.rows[session_id]["quadrants"] if q["kind"] == kind)


def _later(row: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """The row after an UPDATE: same id, equal updated_at (Phase 2 has no touch trigger)."""
    return {**row, **changes}


async def test_text_update_shows_for_both_browsers(user, create_user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "old text")
    other = create_user()
    await other.open(PATH_A)
    await user.open(PATH_A)

    get_services().hub._on_card(card_event(_later(row, text="new text"), "UPDATE", old=row))

    for browser in (user, other):
        assert _card_texts(browser, "IS") == ["new text"]
        await browser.should_not_see("old text")


async def test_quadrant_change_moves_card(user, create_user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "wanderer")
    other = create_user()
    await other.open(PATH_A)
    await user.open(PATH_A)
    for browser in (user, other):
        with browser.scope(marker="quadrant-IS"):
            await browser.should_not_see(EMPTY)
        with browser.scope(marker="quadrant-DOES"):
            await browser.should_see(EMPTY)

    moved = _later(row, quadrant_id=_quadrant_id(repo, SEEDED_ID_A, "DOES"))
    get_services().hub._on_card(card_event(moved, "UPDATE", old=row))

    for browser in (user, other):
        assert _card_texts(browser, "IS") == []
        assert _card_texts(browser, "DOES") == ["wanderer"]
        with browser.scope(marker="quadrant-IS"):
            await browser.should_see(EMPTY)
        with browser.scope(marker="quadrant-DOES"):
            await browser.should_not_see(EMPTY)


async def test_soft_delete_and_hard_delete_remove_card(user, create_user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    soft = seed_card(repo, SEEDED_ID_A, "IS", "soft", order_index=1024.0)
    hard = seed_card(repo, SEEDED_ID_A, "IS", "hard", order_index=2048.0)
    keep = seed_card(repo, SEEDED_ID_A, "IS", "keep", order_index=3072.0)
    other = create_user()
    await other.open(PATH_A)
    await user.open(PATH_A)
    hub = get_services().hub

    stamp = datetime.fromisoformat(soft["created_at"]).isoformat()
    hub._on_card(card_event(_later(soft, deleted_at=stamp), "UPDATE", old=soft))
    for browser in (user, other):
        assert _card_texts(browser, "IS") == ["hard", "keep"]

    hub._on_card(card_event({}, "DELETE", old=hard))  # replica identity full: old_record only
    for browser in (user, other):
        assert _card_texts(browser, "IS") == ["keep"]
        await browser.should_not_see("hard")

    assert keep["id"] in {
        c.id for c in await get_services().sessions.list_cards(keep["workspace_id"])
    }


async def test_deleting_the_last_card_brings_the_hint_back(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "only one")
    await user.open(PATH_A)
    with user.scope(marker="quadrant-IS"):
        await user.should_not_see(EMPTY)

    get_services().hub._on_card(card_event({}, "DELETE", old=row))

    with user.scope(marker="quadrant-IS"):
        await user.should_see(EMPTY)


async def test_stale_update_is_ignored(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "current")
    await user.open(PATH_A)
    older = (datetime.fromisoformat(row["updated_at"]) - timedelta(seconds=1)).isoformat()
    newer = (datetime.fromisoformat(row["updated_at"]) + timedelta(seconds=1)).isoformat()
    hub = get_services().hub

    hub._on_card(card_event(_later(row, text="stale", updated_at=older), "UPDATE", old=row))
    assert _card_texts(user, "IS") == ["current"]

    hub._on_card(card_event(_later(row, text="fresh", updated_at=newer), "UPDATE", old=row))
    assert _card_texts(user, "IS") == ["fresh"]


async def test_identical_cards_both_shown(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)
    hub = get_services().hub

    for _ in range(2):
        hub._on_card(card_event(seed_card(repo, SEEDED_ID_A, "IS", "same", author="Ann")))

    assert _card_texts(user, "IS") == ["same", "same"]
    assert len(user.find(marker="card").elements) == 2


async def test_events_land_in_sort_order(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)
    hub = get_services().hub
    rows = [
        seed_card(repo, SEEDED_ID_A, "IS", "2048", order_index=2048.0),
        seed_card(
            repo,
            SEEDED_ID_A,
            "IS",
            "1024-later",
            order_index=1024.0,
            created_at="2026-10-23T10:00:09+00:00",
        ),
        seed_card(
            repo,
            SEEDED_ID_A,
            "IS",
            "1024-earlier",
            order_index=1024.0,
            created_at="2026-10-23T10:00:01+00:00",
        ),
    ]

    for row in rows:  # arrival order differs from display order
        hub._on_card(card_event(row))

    assert _card_texts(user, "IS") == ["1024-earlier", "1024-later", "2048"]
    listed = await get_services().sessions.list_cards(rows[0]["workspace_id"])
    assert [c.text for c in listed] == _card_texts(user, "IS")


async def test_first_event_fills_an_empty_quadrant(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)
    with user.scope(marker="quadrant-DOES"):
        await user.should_see(EMPTY)

    get_services().hub._on_card(card_event(seed_card(repo, SEEDED_ID_A, "DOES", "first")))

    with user.scope(marker="quadrant-DOES"):
        await user.should_see("first")
        await user.should_not_see(EMPTY)


async def test_update_across_sessions_leaves_old_canvas_and_fills_new(user, create_user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    row = seed_card(repo, SEEDED_ID_A, "IS", "traveller")
    page_b = create_user()
    await page_b.open(PATH_B)
    await user.open(PATH_A)
    assert _card_texts(user, "IS") == ["traveller"]
    workspace_b = repo.rows[SEEDED_ID_B]["id"]

    moved = _later(row, workspace_id=workspace_b, quadrant_id=_quadrant_id(repo, SEEDED_ID_B, "IS"))
    get_services().hub._on_card(card_event(moved, "UPDATE", old=row))

    assert _card_texts(user, "IS") == []
    assert _card_texts(page_b, "IS") == ["traveller"]
    with user.scope(marker="quadrant-IS"):
        await user.should_see(EMPTY)


async def test_event_without_open_canvas_is_harmless(user, caplog):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A, SEEDED_ID_B: SEEDED_NAME_B})
    await user.open(PATH_A)
    row = seed_card(repo, SEEDED_ID_B, "IS", "nobody is looking")

    with caplog.at_level(logging.INFO):
        get_services().hub._on_card(card_event(row))
        get_services().hub._on_card(card_event({}, "DELETE", old=row))

    assert logging.ERROR not in [r.levelno for r in caplog.records]
    assert _card_texts(user, "IS") == []
