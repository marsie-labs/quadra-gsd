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


# --- cards fan-out (02-03): INSERT / UPDATE / DELETE routing through the real channel ---


class RecordingListener:
    """A CardListener that records what the hub hands it."""

    def __init__(self, workspace_id: str, fail: bool = False) -> None:
        self.workspace_id = workspace_id
        self.fail = fail
        self.applied: list = []
        self.removed: list[str] = []

    def apply_card(self, card) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.applied.append(card)

    def remove_card(self, card_id: str) -> None:
        self.removed.append(card_id)


def _row(workspace_id: str = "W1", card_id: str = "c1", **overrides) -> dict:
    row = {
        "id": card_id,
        "workspace_id": workspace_id,
        "quadrant_id": "q1",
        "text": "hello",
        "author": "Ann",
        "order_index": 1024.0,
        "created_at": "2026-10-23T10:00:00+00:00",
        "updated_at": "2026-10-23T10:00:00+00:00",
        "deleted_at": None,
    }
    row.update(overrides)
    return row


def _card_message(
    topic: str,
    event_type: str,
    record: dict,
    old_record: dict | None = None,
    binding_id: int = 8,
) -> dict:
    return {
        "topic": topic,
        "event": "postgres_changes",
        "ref": None,
        "payload": {
            "ids": [binding_id],
            "data": {
                "schema": "public",
                "table": "cards",
                "commit_timestamp": "2026-10-23T10:00:00Z",
                "type": event_type,
                "errors": None,
                "columns": [{"name": "id", "type": "uuid"}],
                "record": record,
                "old_record": old_record or {},
            },
        },
    }


def _deliver_card(hub: RealtimeHub, event_type: str, record: dict, old_record=None) -> None:
    """Feed a cards message through the real channel with the server-assigned binding ids."""
    ch = hub._build_channel()
    ch.postgres_changes_callbacks[0].id = 7
    ch.postgres_changes_callbacks[1].id = 8
    msg = _card_message(ch.topic, event_type, record, old_record)
    ch._handle_message(ServerMessageAdapter.validate_json(json.dumps(msg)))


async def test_cards_message_reaches_on_card_through_channel(hub):
    waiter = hub._register_waiter("abc")
    w1, w2 = RecordingListener("W1"), RecordingListener("W2")
    hub.register(w1)
    hub.register(w2)

    _deliver_card(hub, "INSERT", _row("W1"))

    assert [c.id for c in w1.applied] == ["c1"]
    assert w2.applied == []
    assert not waiter.done()  # the probe waiter is untouched by a cards message


async def test_probe_message_does_not_reach_card_listeners(hub):
    listener = RecordingListener("W1")
    hub.register(listener)
    waiter = hub._register_waiter("abc")

    _deliver(hub, "abc")

    assert waiter.done()
    assert listener.applied == [] and listener.removed == []


def test_delete_event_removes_by_old_record(hub):
    w1, w2 = RecordingListener("W1"), RecordingListener("W2")
    hub.register(w1)
    hub.register(w2)

    _deliver_card(hub, "DELETE", {}, old_record=_row("W1", "gone"))

    assert w1.removed == ["gone"]
    assert w2.removed == []
    assert w1.applied == []


def test_delete_with_only_the_primary_key_removes_from_every_canvas(hub):
    """Hosted RLS sends old_record = {"id": ...} only (measured against the hosted project)."""
    w1, w2 = RecordingListener("W1"), RecordingListener("W2")
    hub.register(w1)
    hub.register(w2)

    _deliver_card(hub, "DELETE", {}, old_record={"id": "gone"})

    assert w1.removed == ["gone"]
    assert w2.removed == ["gone"]


def test_update_across_workspaces_removes_from_old_session(hub):
    w1, w2 = RecordingListener("W1"), RecordingListener("W2")
    hub.register(w1)
    hub.register(w2)

    _deliver_card(hub, "UPDATE", _row("W2"), old_record=_row("W1"))

    assert w1.removed == ["c1"]
    assert w1.applied == []
    assert [c.id for c in w2.applied] == ["c1"]
    assert w2.removed == []


def test_update_inside_one_workspace_does_not_remove(hub):
    w1 = RecordingListener("W1")
    hub.register(w1)

    _deliver_card(hub, "UPDATE", _row("W1", text="new"), old_record={"id": "c1"})

    assert w1.removed == []
    assert [c.text for c in w1.applied] == ["new"]


def test_failing_listener_does_not_block_others(hub, caplog):
    bad, good = RecordingListener("W1", fail=True), RecordingListener("W1")
    hub.register(bad)
    hub.register(good)

    with caplog.at_level(logging.INFO):
        hub._on_card({"data": {"type": "INSERT", "record": _row("W1"), "old_record": {}}})

    assert [c.id for c in good.applied] == ["c1"]
    levels = [r.levelno for r in caplog.records]
    assert levels.count(logging.WARNING) == 1
    assert logging.ERROR not in levels


def test_malformed_event_is_dropped_without_payload_in_logs(hub, caplog):
    listener = RecordingListener("W1")
    hub.register(listener)
    bad = _row("W1", text="PAYLOAD-MARKER-123")
    del bad["order_index"]

    with caplog.at_level(logging.INFO):
        hub._on_card({"data": {"type": "INSERT", "record": bad, "old_record": {}}})
        hub._on_card({"data": {"type": "BOGUS", "record": _row("W1"), "old_record": {}}})
        hub._on_card("not even a dict")
        hub._on_card({"data": {"type": "DELETE", "record": {}, "old_record": {}}})

    assert "PAYLOAD-MARKER-123" not in caplog.text
    assert listener.applied == [] and listener.removed == []
    assert [r.levelno for r in caplog.records].count(logging.WARNING) == 4
    assert logging.ERROR not in [r.levelno for r in caplog.records]

    hub._on_card({"data": {"type": "INSERT", "record": _row("W1", card_id="ok"), "old_record": {}}})
    assert [c.id for c in listener.applied] == ["ok"]


def test_register_unregister_idempotent(hub):
    a, b = RecordingListener("W1"), RecordingListener("W2")
    hub.register(a)
    hub.register(a)
    hub.register(b)
    assert hub.listener_count("W1") == 1
    assert hub.listener_count() == 2

    hub.unregister(a)
    hub.unregister(a)
    assert hub.listener_count("W1") == 0
    assert hub.listener_count() == 1


def test_listener_unregistering_during_dispatch_is_safe(hub):
    class Leaver(RecordingListener):
        def apply_card(self, card) -> None:
            hub.unregister(self)
            super().apply_card(card)

    leaver, stayer = Leaver("W1"), RecordingListener("W1")
    hub.register(leaver)
    hub.register(stayer)

    _deliver_card(hub, "INSERT", _row("W1"))

    assert len(leaver.applied) == 1
    assert len(stayer.applied) == 1
