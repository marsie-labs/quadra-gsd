"""RealtimeHub: owns the Supabase Realtime connection, the canvas registry and the fan-out.

One ``AsyncRealtimeClient``, one channel. Open canvases register as listeners keyed by their
workspace_id; a ``cards`` Postgres Changes event is routed to the listeners of the row's own
workspace only. The hub never reads the database. The startup check proves that a database change
event reaches this process: it upserts a ``realtime_probe`` row carrying a fresh random
nonce and reports ``verified`` only when the Postgres Changes event for *that* nonce arrives.
A merely SUBSCRIBED channel is never reported as success.

Secrets: the Realtime key travels in the WebSocket URL query (``?apikey=``). The client URL
and the key are never logged, and every stored or logged error is passed through ``_sanitize``.
"""

import asyncio
import logging
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

from pydantic import ValidationError
from realtime import AsyncRealtimeChannel, AsyncRealtimeClient
from realtime.types import RealtimePostgresChangesListenEvent, RealtimeSubscribeStates

from app.models import CardView

logger = logging.getLogger(__name__)

CHANNEL_TOPIC = "quadra-db"
StartupStage = Literal["connect", "subscribe", "probe-write", "no-event"]

# realtime-py logs the WebSocket URL (with the key in its query) at DEBUG. Hold these at INFO.
for _noisy in ("realtime", "websockets"):
    _noisy_logger = logging.getLogger(_noisy)
    if _noisy_logger.getEffectiveLevel() < logging.INFO:
        _noisy_logger.setLevel(logging.INFO)

_APIKEY_RE = re.compile(r"(apikey=)[^&\s'\"]+", re.IGNORECASE)

_FIXES = (
    "Likely fixes: (1) if Realtime rejects the sb_secret_ key, set SUPABASE_REALTIME_KEY to the "
    "legacy service_role JWT (Dashboard -> Project Settings -> API Keys -> Legacy API keys); "
    "(2) confirm the init migration is pushed so realtime_probe is in the supabase_realtime "
    "publication (supabase migration list --linked); set REALTIME_CHECK=warn to start anyway."
)


class CardListener(Protocol):
    """An open canvas: receives the cards of its own workspace."""

    workspace_id: str

    def apply_card(self, card: CardView) -> None: ...

    def remove_card(self, card_id: str) -> None: ...


class RealtimeCheckError(RuntimeError):
    """The Realtime startup check failed at a named stage."""

    def __init__(self, stage: StartupStage, detail: str) -> None:
        super().__init__(f"Realtime startup check failed at stage '{stage}': {detail}. {_FIXES}")
        self.stage: StartupStage = stage
        self.detail = detail


class RealtimeHub:
    def __init__(self, supabase_url: str, key: str) -> None:
        # An https URL is accepted and becomes wss. The key lands in the ?apikey= query.
        self._rt = AsyncRealtimeClient(f"{supabase_url.rstrip('/')}/realtime/v1", token=key)
        self._key = key  # kept only to sanitize text
        self.state: str = "pending"
        self.stage: StartupStage | None = None
        self.error: str | None = None
        self.latency_ms: float | None = None
        self._waiters: dict[str, asyncio.Future[float]] = {}
        self._channel: AsyncRealtimeChannel | None = None
        self._listeners: dict[str, set[CardListener]] = {}

    def register(self, listener: CardListener) -> None:
        self._listeners.setdefault(listener.workspace_id, set()).add(listener)

    def unregister(self, listener: CardListener) -> None:
        """Idempotent: unknown listeners are ignored; empty workspace sets are dropped."""
        listeners = self._listeners.get(listener.workspace_id)
        if listeners is None:
            return
        listeners.discard(listener)
        if not listeners:
            del self._listeners[listener.workspace_id]

    def listener_count(self, workspace_id: str | None = None) -> int:
        if workspace_id is None:
            return sum(len(v) for v in self._listeners.values())
        return len(self._listeners.get(workspace_id, ()))

    def _sanitize(self, text: str) -> str:
        if self._key:
            text = text.replace(self._key, "***")
        return _APIKEY_RE.sub(r"\1***", text)

    def _build_channel(self) -> AsyncRealtimeChannel:
        """Create the channel with every binding. All bindings must precede the one subscribe()."""
        channel = self._rt.channel(CHANNEL_TOPIC)
        channel.on_postgres_changes(
            RealtimePostgresChangesListenEvent.All,
            self._on_probe,
            table="realtime_probe",
            schema="public",
        )
        channel.on_postgres_changes(
            RealtimePostgresChangesListenEvent.All,
            self._on_card,
            table="cards",
            schema="public",
        )
        # Later plans add the workspaces binding here, before subscribe().
        return channel

    def _on_card(self, payload: Any) -> None:
        """Plain def (called synchronously in the socket loop): fan a card change out to canvases.

        INSERT/UPDATE apply the row to its workspace's canvases (an UPDATE that changes
        workspace first removes the card from the old workspace's canvases). DELETE carries only
        ``old_record`` (at least the card id) and removes the card. Never raises and never logs
        the payload: a malformed event costs one warning naming the event type and exception class.
        """
        event_type = "unknown"
        try:
            data = payload["data"]
            raw_type = data["type"]
            raw_type = str(getattr(raw_type, "value", raw_type))
            if raw_type == "DELETE":
                event_type = raw_type
                old = data["old_record"]
                card_id = str(old["id"])
                workspace_id = old.get("workspace_id")
                if workspace_id is not None:
                    self._fan_out(str(workspace_id), lambda listener: listener.remove_card(card_id))
                else:
                    # Hosted Postgres Changes sends only the primary key in a DELETE's old_record
                    # when RLS is on, even with replica identity full (measured in 02-03). Card
                    # ids are globally unique and removal of an unknown id is a no-op, so tell
                    # every open canvas: it can only ever drop a card it already shows.
                    for workspace in list(self._listeners):
                        self._fan_out(workspace, lambda listener: listener.remove_card(card_id))
                return
            if raw_type not in ("INSERT", "UPDATE"):
                raise ValueError("unknown event type")
            event_type = raw_type
            card = CardView.model_validate(data["record"])
            old_workspace_id = None
            if raw_type == "UPDATE":
                old_record = data.get("old_record")
                if isinstance(old_record, dict):
                    old_workspace_id = old_record.get("workspace_id")
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError) as exc:
            logger.warning("ignored cards event %s: %s", event_type, type(exc).__name__)
            return
        if old_workspace_id is not None and old_workspace_id != card.workspace_id:
            self._fan_out(str(old_workspace_id), lambda listener: listener.remove_card(card.id))
        self._fan_out(card.workspace_id, lambda listener: listener.apply_card(card))

    def _fan_out(self, workspace_id: str, call: Callable[[CardListener], None]) -> None:
        """Call every listener of one workspace; one failing canvas never blocks the others."""
        for listener in list(self._listeners.get(workspace_id, ())):
            try:
                call(listener)
            except Exception as exc:
                logger.warning("canvas listener failed: %s", type(exc).__name__)

    def _on_probe(self, payload: Any) -> None:
        """Plain def: realtime-py calls it synchronously inside the socket listen loop."""
        try:
            nonce = payload["data"]["record"]["nonce"]
        except (KeyError, TypeError):
            return
        waiter = self._waiters.get(nonce)
        if waiter is not None and not waiter.done():
            waiter.set_result(time.monotonic())

    def _register_waiter(self, nonce: str) -> asyncio.Future[float]:
        waiter: asyncio.Future[float] = asyncio.get_running_loop().create_future()
        self._waiters[nonce] = waiter
        return waiter

    async def start(self, timeout: float = 15.0) -> None:
        """Connect and subscribe the single channel; raise RealtimeCheckError on failure."""
        try:
            await self._rt.connect()
        except Exception as exc:
            raise RealtimeCheckError(
                "connect", self._sanitize(f"{type(exc).__name__}: {exc}")
            ) from None

        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def on_state(state: RealtimeSubscribeStates, err: Exception | None) -> None:
            if ready.done():
                return  # re-join notifications after startup are a Phase 2 concern (resync)
            if state is RealtimeSubscribeStates.SUBSCRIBED:
                ready.set_result(None)
            else:
                ready.set_exception(RuntimeError(f"{state.value}: {err}"))

        try:
            self._channel = self._build_channel()
            await self._channel.subscribe(on_state)
            await asyncio.wait_for(ready, timeout)
        except TimeoutError:
            raise RealtimeCheckError(
                "subscribe", f"channel not SUBSCRIBED within {timeout:.0f}s"
            ) from None
        except Exception as exc:
            raise RealtimeCheckError(
                "subscribe", self._sanitize(f"{type(exc).__name__}: {exc}")
            ) from None

    async def verify_roundtrip(
        self,
        write_probe: Callable[[str], Awaitable[None]],
        timeout: float = 15.0,
        resend_every: float = 3.0,
    ) -> float:
        """Write a probe row until its nonce comes back as a Realtime event. Returns ms.

        The bounded re-write (at most timeout/resend_every writes, startup only) covers a
        channel that is SUBSCRIBED before change data capture is flowing. It never reads rows
        back: success comes only from the Realtime event.
        """
        nonce = secrets.token_hex(8)
        waiter = self._register_waiter(nonce)
        started = time.monotonic()
        try:
            while True:
                try:
                    await write_probe(nonce)
                except Exception as exc:
                    raise RealtimeCheckError(
                        "probe-write", self._sanitize(f"{type(exc).__name__}: {exc}")
                    ) from None
                remaining = timeout - (time.monotonic() - started)
                if remaining > 0:
                    try:
                        await asyncio.wait_for(asyncio.shield(waiter), min(resend_every, remaining))
                        break
                    except TimeoutError:
                        pass
                if time.monotonic() - started >= timeout:
                    raise RealtimeCheckError(
                        "no-event",
                        f"no realtime_probe change event arrived within {timeout:.0f}s",
                    )
        finally:
            self._waiters.pop(nonce, None)
        return (waiter.result() - started) * 1000

    async def run_startup_check(
        self,
        mode: Literal["strict", "warn", "off"],
        write_probe: Callable[[str], Awaitable[None]],
        timeout: float = 15.0,
    ) -> None:
        """strict: raise on failure. warn: log one ERROR and continue. off: do nothing."""
        if mode == "off":
            self.state = "disabled"
            logger.info("Realtime startup check disabled (REALTIME_CHECK=off)")
            return
        try:
            await self.start(timeout)
            latency_ms = await self.verify_roundtrip(write_probe, timeout)
        except RealtimeCheckError as exc:
            self.state = "failed"
            self.stage = exc.stage
            self.latency_ms = None
            self.error = self._sanitize(exc.detail)
            failure = RealtimeCheckError(exc.stage, self.error)
            if mode == "strict":
                await self.stop()
                raise failure from None
            logger.error("%s", failure)
            return
        # Only a nonce-matched change event gets here; SUBSCRIBED alone never verifies.
        self.state = "verified"
        self.stage = None
        self.error = None
        self.latency_ms = latency_ms
        logger.info(
            "Realtime startup check verified: DB change event received in %.0f ms", latency_ms
        )

    async def stop(self) -> None:
        try:
            await self._rt.close()
        except Exception as exc:
            logger.warning("Realtime client close failed: %s", type(exc).__name__)

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "stage": self.stage,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }
