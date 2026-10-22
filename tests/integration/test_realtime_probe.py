"""Live proof (hosted Supabase) that a DB change event reaches the Python server via Realtime."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.db.repository import Repository
from app.realtime.hub import RealtimeHub

pytestmark = pytest.mark.integration


async def test_probe_roundtrip_via_hub(integration_settings, supabase_client):
    hub = RealtimeHub(integration_settings.supabase_url, integration_settings.realtime_key())
    try:
        await hub.run_startup_check("strict", Repository(supabase_client).upsert_probe, timeout=20)
        assert hub.state == "verified"
        assert hub.latency_ms is not None
        assert 0 < hub.latency_ms < 20000
    finally:
        await hub.stop()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_app_starts_and_proves_realtime(integration_settings, tmp_path):
    port = _free_port()
    log_path = tmp_path / "app.log"
    repo_root = Path(__file__).resolve().parents[2]
    with log_path.open("wb") as log_file:
        proc = subprocess.Popen(
            [sys.executable, "-m", "app"],
            cwd=repo_root,
            env={**os.environ, "APP_PORT": str(port), "REALTIME_CHECK": "strict"},
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            health: dict | None = None
            # Wait for the subprocess to boot (bind its port and finish the lifespan). This is a
            # test-harness readiness probe, not an app-level polling pattern.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                try:
                    resp = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=2)
                except httpx.HTTPError:
                    time.sleep(0.5)
                    continue
                health = resp.json()
                break
            if health is None:
                tail = _sanitized_log(log_path, integration_settings)[-2000:]
                pytest.fail(f"app did not come up (exit={proc.poll()}). Log tail:\n{tail}")

            assert health["realtime"]["state"] == "verified"
            assert health["status"] == "ok"

            home = httpx.get(f"http://127.0.0.1:{port}/", timeout=10)
            assert home.status_code == 200
            assert "max-age=31536000" in home.headers.get("set-cookie", "").lower()
        finally:
            proc.terminate()
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    log_text = log_path.read_text(errors="replace")
    assert "Realtime startup check verified" in log_text
    assert integration_settings.supabase_secret_key.get_secret_value() not in log_text
    assert integration_settings.realtime_key() not in log_text
    assert "apikey=" not in log_text


def _sanitized_log(log_path: Path, settings) -> str:
    text = log_path.read_text(errors="replace")
    for secret in (settings.supabase_secret_key.get_secret_value(), settings.realtime_key()):
        text = text.replace(secret, "<redacted>")
    return text
