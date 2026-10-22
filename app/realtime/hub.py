"""RealtimeHub (RED stub): signatures only, behavior arrives in the GREEN commit."""

from typing import Literal

CHANNEL_TOPIC = "quadra-db"
StartupStage = Literal["connect", "subscribe", "probe-write", "no-event"]


class RealtimeCheckError(RuntimeError):
    def __init__(self, stage: StartupStage, detail: str) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


class RealtimeHub:
    def __init__(self, supabase_url: str, key: str) -> None:
        self.state = "pending"
        self.stage: StartupStage | None = None
        self.error: str | None = None
        self.latency_ms: float | None = None

    def _build_channel(self):
        raise NotImplementedError

    def _on_probe(self, payload) -> None:
        raise NotImplementedError

    def _register_waiter(self, nonce: str):
        raise NotImplementedError

    async def start(self, timeout: float = 15.0) -> None:
        raise NotImplementedError

    async def verify_roundtrip(self, write_probe, timeout=15.0, resend_every=3.0) -> float:
        raise NotImplementedError

    async def run_startup_check(self, mode, write_probe, timeout=15.0) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def status(self) -> dict:
        raise NotImplementedError
