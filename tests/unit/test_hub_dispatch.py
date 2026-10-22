"""RealtimeHub offline proof: nonce dispatch, bounded waits, strict/warn/off failure handling."""

import asyncio
import inspect
import json
import logging

import pytest
from realtime.message import ServerMessageAdapter

from app.realtime.hub import RealtimeCheckError, RealtimeHub

FAKE_KEY = "sb_secret_FAKEKEY123"


@pytest.fixture
def hub() -> RealtimeHub:
    return RealtimeHub("https://example.supabase.co", FAKE_KEY)


def _probe_message(topic: str, nonce: str, event_type: str = "UPDATE") -> dict:
    return {
        "topic": topic,
        "event": "postgres_changes",
        "ref": None,
        "payload": {
            "ids": [7],
            "data": {
                "schema": "public",
                "table": "realtime_probe",
                "commit_timestamp": "2026-10-22T10:00:00Z",
                "type": event_type,
                "errors": None,
                "columns": [{"name": "id", "type": "int2"}],
                "record": {"id": 1, "nonce": nonce},
                "old_record": {"id": 1},
            },
        },
    }


def _deliver(hub: RealtimeHub, nonce: str, event_type: str = "UPDATE") -> None:
    """Feed a postgres_changes message through the channel exactly as the socket loop does."""
    ch = hub._build_channel()
    ch.postgres_changes_callbacks[0].id = 7  # normally set by the join reply
    msg = _probe_message(ch.topic, nonce, event_type)
    ch._handle_message(ServerMessageAdapter.validate_json(json.dumps(msg)))


@pytest.mark.parametrize("event_type", ["UPDATE", "INSERT"])
async def test_matching_nonce_resolves_waiter(hub, event_type):
    waiter = hub._register_waiter("abc")
    _deliver(hub, "abc", event_type)
    assert waiter.done()
    assert waiter.result() > 0


async def test_non_matching_nonce_leaves_waiter_pending(hub):
    waiter = hub._register_waiter("abc")
    _deliver(hub, "someone-elses-nonce")
    assert not waiter.done()


def test_on_probe_is_plain_def():
    assert not inspect.iscoroutinefunction(RealtimeHub._on_probe)


async def test_verify_roundtrip_returns_latency(hub):
    async def write_probe(nonce: str) -> None:
        asyncio.get_running_loop().call_later(0.05, _deliver, hub, nonce)

    latency = await hub.verify_roundtrip(write_probe, timeout=2.0, resend_every=1.0)
    assert latency >= 0


async def test_verify_roundtrip_times_out_with_no_event_after_resends(hub):
    calls: list[str] = []

    async def write_probe(nonce: str) -> None:
        calls.append(nonce)  # the write succeeds but no event ever arrives

    with pytest.raises(RealtimeCheckError) as exc:
        await hub.verify_roundtrip(write_probe, timeout=0.3, resend_every=0.1)
    assert exc.value.stage == "no-event"
    assert len(calls) >= 2
    assert len(set(calls)) == 1  # re-writes reuse this run's nonce
    assert hub._waiters == {}


async def test_probe_write_failure_is_staged(hub):
    async def write_probe(nonce: str) -> None:
        raise ConnectionError(f"boom {FAKE_KEY}")

    with pytest.raises(RealtimeCheckError) as exc:
        await hub.verify_roundtrip(write_probe, timeout=0.3, resend_every=0.1)
    assert exc.value.stage == "probe-write"
    assert FAKE_KEY not in str(exc.value)


async def test_off_mode_is_disabled_without_connecting(hub, monkeypatch):
    async def must_not_connect(*args, **kwargs):
        raise AssertionError("off mode must not connect")

    monkeypatch.setattr(hub._rt, "connect", must_not_connect)
    monkeypatch.setattr(hub, "start", must_not_connect)

    await hub.run_startup_check("off", must_not_connect)
    assert hub.state == "disabled"


def _failing_start(hub: RealtimeHub, monkeypatch) -> None:
    async def start(timeout: float = 15.0) -> None:
        raise RealtimeCheckError(
            "connect", f"refused {FAKE_KEY} wss://x/websocket?apikey={FAKE_KEY}"
        )

    monkeypatch.setattr(hub, "start", start)


async def test_warn_check_failure_records_failed_without_key(hub, monkeypatch, caplog):
    _failing_start(hub, monkeypatch)

    async def write_probe(nonce: str) -> None:
        raise AssertionError("never reached")

    with caplog.at_level(logging.INFO):
        await hub.run_startup_check("warn", write_probe)

    assert hub.state == "failed"
    assert hub.stage == "connect"
    assert hub.error and FAKE_KEY not in hub.error
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert FAKE_KEY not in caplog.text


async def test_strict_check_failure_raises_with_stage_and_fix(hub, monkeypatch):
    _failing_start(hub, monkeypatch)

    async def write_probe(nonce: str) -> None:
        raise AssertionError("never reached")

    with pytest.raises(RealtimeCheckError) as exc:
        await hub.run_startup_check("strict", write_probe)

    message = str(exc.value)
    assert "connect" in message
    assert "SUPABASE_REALTIME_KEY" in message
    assert FAKE_KEY not in message
    assert hub.state == "failed"


async def test_subscribed_alone_never_verifies(hub, monkeypatch):
    async def start(timeout: float = 15.0) -> None:
        return None  # channel SUBSCRIBED, but no change event will ever arrive

    async def write_probe(nonce: str) -> None:
        return None

    monkeypatch.setattr(hub, "start", start)
    with pytest.raises(RealtimeCheckError) as exc:
        await hub.run_startup_check("strict", write_probe, timeout=0.3)
    assert exc.value.stage == "no-event"
    assert hub.state == "failed"
    assert hub.latency_ms is None


def test_status_has_exactly_four_keys(hub):
    assert set(hub.status()) == {"state", "stage", "latency_ms", "error"}
