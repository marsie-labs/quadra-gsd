"""RealtimeHub recovery, offline: re-join handling, single-flight backoff, sanitizing, shutdown.

No network is used. The tests replace ``hub.start``, ``hub.verify_roundtrip``, ``hub._new_client``
and ``hub._sleep`` with recorders (plain assignment, so a missing hook fails inside the test body).
"""

import asyncio
import logging
from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from realtime.types import RealtimeSubscribeStates

from app.main import health_router
from app.realtime.hub import RealtimeCheckError, RealtimeHub

FAKE_KEY = "sb_secret_FAKEKEY123"
SUBSCRIBED = RealtimeSubscribeStates.SUBSCRIBED
CHANNEL_ERROR = RealtimeSubscribeStates.CHANNEL_ERROR
TIMED_OUT = RealtimeSubscribeStates.TIMED_OUT


class FakeRt:
    """Stands in for AsyncRealtimeClient: a controllable ``_listen_task`` and an async close()."""

    def __init__(self) -> None:
        self._listen_task: asyncio.Future[None] | None = asyncio.get_running_loop().create_future()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class Rig:
    """Recorders wired into a hub: start, verify, sleep and the listeners' resync requests."""

    def __init__(self, hub: RealtimeHub) -> None:
        self.hub = hub
        self.events: list[str] = []
        self.sleeps: list[float] = []
        self.clients: list[FakeRt] = []
        self.fail_starts = 0
        self.fail_verifies = 0
        self.latency = 0.0
        hub._rt = self.new_client()
        hub._new_client = self.new_client
        hub.start = self.start
        hub.verify_roundtrip = self.verify
        hub._sleep = self.sleep

    def new_client(self) -> FakeRt:
        client = FakeRt()
        self.clients.append(client)
        return client

    async def start(self, timeout: float = 15.0) -> None:
        self.events.append("start")
        if self.fail_starts > 0:
            self.fail_starts -= 1
            raise RealtimeCheckError(
                "connect", f"refused {FAKE_KEY} wss://x/websocket?apikey={FAKE_KEY}"
            )

    async def verify(self, write_probe, timeout: float = 15.0, resend_every: float = 3.0) -> float:
        self.events.append("verify")
        if self.fail_verifies > 0:
            self.fail_verifies -= 1
            raise RealtimeCheckError("no-event", f"no event {FAKE_KEY}")
        self.latency += 10.0
        return self.latency

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        await asyncio.sleep(0)  # a real sleep yields to the loop; so does this one

    def listener(self, name: str, workspace_id: str = "W1", fail: bool = False) -> "Listener":
        listener = Listener(name, workspace_id, self.events, fail)
        self.hub.register(listener)
        return listener


class Listener:
    def __init__(self, name: str, workspace_id: str, events: list[str], fail: bool) -> None:
        self.name = name
        self.workspace_id = workspace_id
        self._events = events
        self._fail = fail

    def apply_card(self, card) -> None:
        pass

    def remove_card(self, card_id: str) -> None:
        pass

    def request_resync(self) -> None:
        self._events.append(f"resync:{self.name}")
        if self._fail:
            raise RuntimeError("boom")


async def _write_probe(nonce: str) -> None:
    return None


@pytest.fixture
async def rig():
    hub = RealtimeHub("https://example.supabase.co", FAKE_KEY)
    rig = Rig(hub)
    yield rig
    await hub.stop()


async def _until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    """Test-harness wait for a background task to reach a state (not an app polling pattern)."""

    async def wait() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait(), timeout)


async def _verified_rig(rig: Rig) -> Rig:
    await rig.hub.run_startup_check("strict", _write_probe)
    assert rig.hub.state == "verified"
    rig.events.clear()
    return rig


async def test_rejoin_subscribed_reverifies_then_resyncs(rig):
    hub = rig.hub
    rig.listener("a")
    rig.listener("b", workspace_id="W2")
    await _verified_rig(rig)
    first_latency = hub.latency_ms

    hub._on_channel_state(SUBSCRIBED, None)
    await hub._resubscribe_task

    assert hub.state == "verified"
    assert hub.latency_ms is not None and hub.latency_ms != first_latency
    assert rig.events[0] == "verify"
    assert sorted(rig.events[1:]) == ["resync:a", "resync:b"]  # once each, after the verify


async def test_channel_error_starts_one_recovery(rig):
    hub = rig.hub
    rig.listener("a")
    await _verified_rig(rig)

    hub._on_channel_state(CHANNEL_ERROR, RuntimeError("x"))
    hub._on_channel_state(CHANNEL_ERROR, RuntimeError("y"))
    hub._on_channel_state(TIMED_OUT, None)
    assert hub.state == "reconnecting"
    await hub._recovery_task

    assert rig.events == ["start", "verify", "resync:a"]
    assert hub.state == "verified"
    assert len(rig.clients) == 2  # the original and exactly one rebuilt client
    assert rig.clients[0].closed


async def test_recovery_backoff_sequence(rig):
    hub = rig.hub
    await _verified_rig(rig)
    rig.fail_starts = 7

    hub._on_channel_state(CHANNEL_ERROR, None)
    await hub._recovery_task

    assert rig.sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    assert hub.state == "verified"
    assert hub.error is None and hub.stage is None


async def test_recovery_logs_and_errors_are_sanitized(rig, caplog):
    hub = rig.hub
    await _verified_rig(rig)
    rig.fail_starts = 10_000

    with caplog.at_level(logging.INFO):
        hub._on_channel_state(CHANNEL_ERROR, RuntimeError(f"apikey={FAKE_KEY}"))
        await _until(lambda: len(rig.sleeps) >= 3)
        status_text = str(hub.status())
        error_text = hub.error or ""
        log_text = caplog.text

    assert hub.state == "reconnecting"
    for text in (log_text, error_text, status_text):
        assert FAKE_KEY not in text
        assert "apikey=sb_" not in text
    assert error_text  # something useful is stored
    assert logging.ERROR not in [r.levelno for r in caplog.records]


async def test_failed_reverify_after_rejoin_starts_recovery(rig):
    hub = rig.hub
    rig.listener("a")
    await _verified_rig(rig)
    rig.fail_verifies = 1

    hub._on_channel_state(SUBSCRIBED, None)
    await hub._resubscribe_task
    assert hub._recovery_task is not None
    await hub._recovery_task

    assert rig.events == ["verify", "start", "verify", "resync:a"]  # no resync before recovery
    assert hub.state == "verified"


async def test_resync_isolated_per_listener(rig, caplog):
    hub = rig.hub
    rig.listener("bad", fail=True)
    rig.listener("good")
    rig.listener("other", workspace_id="W2")

    with caplog.at_level(logging.INFO):
        hub._resync_listeners()

    assert sorted(rig.events) == ["resync:bad", "resync:good", "resync:other"]
    levels = [r.levelno for r in caplog.records]
    assert levels.count(logging.WARNING) == 1
    assert logging.ERROR not in levels


async def test_warn_mode_failure_recovers_to_verified(rig, caplog):
    hub = rig.hub
    rig.listener("a")
    rig.fail_starts = 1

    with caplog.at_level(logging.INFO):
        await hub.run_startup_check("warn", _write_probe)
        assert hub.state == "failed"  # IN-03: it used to stay here for the life of the process
        await hub._recovery_task

    assert hub.state == "verified"
    assert hub.error is None and hub.stage is None
    assert rig.events[-2:] == ["verify", "resync:a"]
    assert [r.levelno for r in caplog.records].count(logging.ERROR) == 1


async def test_stop_cancels_recovery(rig):
    hub = rig.hub
    rig.fail_starts = 10_000
    await hub.run_startup_check("warn", _write_probe)
    await _until(lambda: rig.events.count("start") >= 3)
    recovery = hub._recovery_task

    await hub.stop()

    assert recovery is not None and recovery.done()
    starts = rig.events.count("start")
    for _ in range(20):
        await asyncio.sleep(0)
    assert rig.events.count("start") == starts  # no connection attempt after shutdown


async def test_probe_write_is_bounded():
    hub = RealtimeHub("https://example.supabase.co", FAKE_KEY)

    async def hanging_write(nonce: str) -> None:
        await asyncio.sleep(3600)

    with pytest.raises(RealtimeCheckError) as exc:
        await asyncio.wait_for(hub.verify_roundtrip(hanging_write, timeout=0.3), 2)

    assert exc.value.stage == "probe-write"
    assert hub._waiters == {}


async def test_reconnecting_state_is_degraded_on_healthz():
    hub = RealtimeHub("https://example.supabase.co", FAKE_KEY)
    hub.state = "reconnecting"
    app = FastAPI()
    app.include_router(health_router)
    app.state.hub = hub

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get("/healthz")).json()

    assert body["status"] == "degraded"
    assert body["realtime"]["state"] == "reconnecting"
    assert set(body["realtime"]) == {"state", "stage", "latency_ms", "error"}
    assert set(hub.status()) == {"state", "stage", "latency_ms", "error"}


# --- Task 2: a socket that closes silently is noticed by the supervisor ---


def _live_supervisors() -> list[asyncio.Task]:
    return [
        t for t in asyncio.all_tasks() if t.get_name() == "realtime-supervisor" and not t.done()
    ]


def test_listen_task_attribute_exists():
    """The supervisor reads the private realtime 2.33 ``_listen_task``; an upgrade must not hide it."""
    from realtime import AsyncRealtimeClient

    client = AsyncRealtimeClient("https://example.supabase.co/realtime/v1", token="x")
    assert hasattr(client, "_listen_task")


async def test_closed_socket_triggers_recovery(rig):
    hub = rig.hub
    rig.listener("a")
    await _verified_rig(rig)

    rig.clients[0]._listen_task.set_result(None)  # a normal close ends the listen task silently
    await _until(lambda: hub._recovery_task is not None)
    assert hub.state == "reconnecting"
    await hub._recovery_task

    assert rig.events == ["start", "verify", "resync:a"]
    assert hub.state == "verified"


async def test_library_reconnect_does_not_rebuild(rig):
    hub = rig.hub
    await _verified_rig(rig)
    rt = rig.clients[0]
    old = rt._listen_task
    rt._listen_task = asyncio.get_running_loop().create_future()  # realtime-py reconnected itself
    new = rt._listen_task

    old.set_result(None)
    for _ in range(20):
        await asyncio.sleep(0)

    assert hub._recovery_task is None
    assert hub.state == "verified"
    assert not hub._supervisor_task.done()  # still watching, now the new task

    new.set_result(None)  # the new socket dies too: now it is a real loss
    await _until(lambda: hub._recovery_task is not None)
    await hub._recovery_task
    assert hub.state == "verified"


async def test_supervisor_started_after_verified_startup_and_recovery(rig):
    hub = rig.hub
    await _verified_rig(rig)
    assert len(_live_supervisors()) == 1
    first = hub._supervisor_task

    hub._on_channel_state(CHANNEL_ERROR, None)
    await hub._recovery_task
    for _ in range(5):
        await asyncio.sleep(0)

    assert hub._supervisor_task is not first
    assert first.done()
    assert len(_live_supervisors()) == 1


async def test_stop_ends_supervisor(rig):
    hub = rig.hub
    await _verified_rig(rig)
    supervisor = hub._supervisor_task
    rt = rig.clients[0]

    await hub.stop()
    assert supervisor.done()

    rt._listen_task.set_result(None)
    for _ in range(20):
        await asyncio.sleep(0)
    assert hub._recovery_task is None
    assert rig.events == []
