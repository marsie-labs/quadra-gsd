"""SYNC-04 offline proofs: a canvas catches up from the database after missed events.

A real socket reconnect cannot be simulated by the NiceGUI ``user`` fixture. ``_reconnect``
replays one by invoking the page client's ``connect_handlers`` through ``safe_invoke``, the same
list ``Client.handle_handshake`` runs on every handshake. ``user.open`` already performed the
first handshake, so a replay is a second one. A real browser reconnect is an end-of-phase
human check.
"""

import asyncio
import logging

from app.deps import get_services
from app.ui.canvas_view import CanvasView
from tests.ui.fakes import (
    SEEDED_ID_A,
    SEEDED_NAME_A,
    FakeRepository,
    card_event,
    install_fake_services,
    seed_card,
    soft_delete_card,
)

PATH_A = f"/s/{SEEDED_ID_A}"
REFRESH_FAILED = "Could not refresh the cards. Reload the page to try again."


def _card_texts(browser, kind: str) -> list[str]:
    column = next(iter(browser.find(marker=f"cards-{kind}").elements))
    return [card.default_slot.children[0].text for card in column.default_slot.children]


def _reconnect(user) -> None:
    for handler in list(user.client.connect_handlers):
        user.client.safe_invoke(handler)


def _canvas_view(repo: FakeRepository) -> CanvasView:
    hub = get_services().hub
    (view,) = hub._listeners[repo.rows[SEEDED_ID_A]["id"]]
    return view  # type: ignore[return-value]


async def _settle() -> None:
    """Wait until no canvas resync task is running (test-harness wait, not app polling)."""
    for _ in range(100):
        busy = [
            t
            for t in asyncio.all_tasks()
            if t.get_name().startswith("canvas resync") and not t.done()
        ]
        if not busy:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("a canvas resync never finished")


async def test_reopen_after_tab_closed_shows_cards_written_meanwhile(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "before", order_index=1024.0)
    await user.open(PATH_A)
    user.client.delete()

    seed_card(repo, SEEDED_ID_A, "IS", "while away one", order_index=2048.0)
    seed_card(repo, SEEDED_ID_A, "DOES", "while away two")
    await user.open(PATH_A)

    assert _card_texts(user, "IS") == ["before", "while away one"]
    assert _card_texts(user, "DOES") == ["while away two"]


async def test_reconnect_handshake_resyncs_from_db(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    gone = seed_card(repo, SEEDED_ID_A, "IS", "soft deleted while away", order_index=1024.0)
    await user.open(PATH_A)
    await user.should_see("soft deleted while away")

    seed_card(repo, SEEDED_ID_A, "IS", "added while away", order_index=2048.0)
    soft_delete_card(repo, gone["id"])
    _reconnect(user)

    await user.should_see("added while away", retries=40)
    await user.should_not_see("soft deleted while away", retries=40)
    assert _card_texts(user, "IS") == ["added while away"]


async def test_first_handshake_does_not_read_again(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "one")

    await user.open(PATH_A)
    await _settle()

    assert repo.list_calls == 1


async def test_event_during_resync_beats_older_snapshot(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    row = seed_card(repo, SEEDED_ID_A, "IS", "doomed")
    await user.open(PATH_A)
    repo.list_gate = asyncio.Event()
    _reconnect(user)
    for _ in range(100):  # let the resync reach the held read
        if repo.list_calls == 2:
            break
        await asyncio.sleep(0.02)
    assert repo.list_calls == 2

    gone = {**row, "deleted_at": "2999-01-01T00:00:00+00:00"}
    get_services().hub._on_card(card_event(gone, "UPDATE", old=row))
    repo.list_gate.set()  # the held snapshot still contains the card
    await _settle()

    assert _card_texts(user, "IS") == []


async def test_resync_requests_coalesce(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "one")
    await user.open(PATH_A)
    view = _canvas_view(repo)
    before = repo.list_calls
    repo.list_gate = asyncio.Event()

    for _ in range(3):
        view.request_resync()
    await asyncio.sleep(0.2)
    assert repo.list_calls - before == 1  # one read in flight, the rest only queued a rerun
    repo.list_gate.set()
    await _settle()

    assert 1 <= repo.list_calls - before <= 2


async def test_resync_failure_keeps_cards_and_warns(user, caplog):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    seed_card(repo, SEEDED_ID_A, "IS", "survivor")
    await user.open(PATH_A)

    with caplog.at_level(logging.INFO):
        repo.fail_next_list_codes = ["XX000"]
        _reconnect(user)
        await user.should_see(REFRESH_FAILED, retries=40)
        await _settle()

        assert _card_texts(user, "IS") == ["survivor"]
        get_services().hub._on_card(card_event(seed_card(repo, SEEDED_ID_A, "DOES", "later")))
        assert _card_texts(user, "DOES") == ["later"]

    assert logging.ERROR not in [r.levelno for r in caplog.records]
    warnings = [r for r in caplog.records if "canvas resync failed" in r.getMessage()]
    assert len(warnings) == 1
    assert "injected" not in warnings[0].getMessage()


async def test_session_read_failure_returns_503(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    repo.fail_next_get_codes = ["XX000"]

    response = await user.http_client.get(PATH_A)

    assert response.status_code == 503
    assert "Temporarily unavailable" in response.text
    assert "Session not found" not in response.text


async def test_card_read_failure_returns_503_and_unregisters(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    repo.fail_next_list_codes = ["XX000"]

    response = await user.http_client.get(PATH_A)

    assert response.status_code == 503
    assert "Temporarily unavailable" in response.text
    assert "Session not found" not in response.text
    assert get_services().hub.listener_count(repo.rows[SEEDED_ID_A]["id"]) == 0


async def test_request_resync_reloads_from_db(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    await user.open(PATH_A)
    view = _canvas_view(repo)

    seed_card(repo, SEEDED_ID_A, "IS_NOT", "found by resync")
    view.request_resync()

    await user.should_see("found by resync", retries=40)
