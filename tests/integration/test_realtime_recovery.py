"""Live proof (hosted Supabase) that a dropped Realtime socket heals and canvases catch up.

The drop is forced by closing the hub's websocket from the client side. That is a normal close:
realtime-py does not reconnect it, which is the 24 h connection-cap path the supervisor exists
for. Recovery is held at a gate so a card can be written while no live socket exists.
"""

import asyncio
import logging
import secrets
import time

import pytest

from app.db.repository import Repository
from app.models import CardView
from app.realtime.hub import RealtimeHub
from app.services.sessions import SessionService
from app.tokens import new_session_id

pytestmark = pytest.mark.integration


class ResyncListener:
    """A canvas stand-in: records live cards and, on request_resync(), re-reads from the DB."""

    def __init__(self, workspace_id: str, service: SessionService) -> None:
        self.workspace_id = workspace_id
        self._service = service
        self.live: asyncio.Queue[str] = asyncio.Queue()
        self.resynced_ids: list[str] = []
        self.resynced = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()

    def apply_card(self, card: CardView) -> None:
        self.live.put_nowait(card.id)

    def remove_card(self, card_id: str) -> None:
        pass

    def request_resync(self) -> None:
        task = asyncio.get_running_loop().create_task(self._resync())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _resync(self) -> None:
        cards = await self._service.list_cards(self.workspace_id)
        self.resynced_ids = [card.id for card in cards]
        self.resynced.set()


async def _wait_until(predicate, timeout: float) -> None:
    """Test-harness wait for the hub's background recovery to reach a state."""
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        await asyncio.sleep(0.05)


async def test_hub_recovers_from_dropped_socket_and_resyncs(
    integration_settings, supabase_client, created_session_ids, caplog
):
    repo = Repository(supabase_client)
    service = SessionService(repo)
    hub = RealtimeHub(integration_settings.supabase_url, integration_settings.realtime_key())
    secrets_in_play = (
        integration_settings.supabase_secret_key.get_secret_value(),
        integration_settings.realtime_key(),
    )
    try:
        with caplog.at_level(logging.INFO):
            await hub.run_startup_check("strict", repo.upsert_probe, timeout=20)

            sid = new_session_id()
            await repo.create_session("IT recovery " + secrets.token_hex(4), sid)
            created_session_ids.append(sid)
            session = await service.get(sid)
            assert session is not None
            quadrant_id = session.quadrants[0].id

            listener = ResyncListener(session.workspace_id, service)
            hub.register(listener)

            gate = asyncio.Event()
            original_start = hub.start

            async def gated_start(timeout: float = 15.0) -> None:
                await gate.wait()
                await original_start(timeout)

            hub.start = gated_start  # type: ignore[method-assign]

            # Force the drop: a normal client-side close that realtime-py will not reconnect.
            await hub._rt._ws_connection.close()
            await _wait_until(lambda: hub.state == "reconnecting", 10)

            # No live socket exists now, so this card can only arrive through the resync.
            missed = await service.add_card(
                session.workspace_id, quadrant_id, "written meanwhile", "Ann"
            )
            assert listener.live.empty()

            opened = time.monotonic()
            gate.set()
            await asyncio.wait_for(listener.resynced.wait(), 60)
            recovery_ms = (time.monotonic() - opened) * 1000
            print(f"\nRECOVERY: gate opened -> verified and canvas resynced: {recovery_ms:.0f} ms")

            assert hub.state == "verified"
            assert missed.id in listener.resynced_ids

            # The rebuilt subscription delivers new cards live again (SYNC-01).
            fresh = await service.add_card(
                session.workspace_id, quadrant_id, "after recovery", "Ann"
            )
            while True:
                arrived = await asyncio.wait_for(listener.live.get(), 5)
                if arrived == fresh.id:
                    break

        text = caplog.text
        leaked = any(secret in text for secret in secrets_in_play) or "apikey=" in text
        assert not leaked, "a key or apikey= value appeared in the recovery logs"
    finally:
        await hub.stop()
