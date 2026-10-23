"""Live proof (hosted Supabase) that a restarted server shows cards written while it was down.

The real app runs as a subprocess, twice. Realtime replays nothing, so everything the second
process shows comes from its page-open database read (SYNC-04).
"""

import asyncio
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.db.repository import Repository
from app.services.sessions import SessionService
from app.tokens import new_session_id

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _sanitized_log(log_path: Path, settings) -> str:
    text = log_path.read_text(errors="replace")
    for secret in (settings.supabase_secret_key.get_secret_value(), settings.realtime_key()):
        text = text.replace(secret, "<redacted>")
    return text


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


async def _wait_verified(proc: subprocess.Popen, port: int, log_path: Path, settings) -> float:
    """Wait until /healthz reports realtime verified; return the seconds that took.

    A test-harness readiness wait (as in test_realtime_probe.py), not app-level polling.
    """
    started = time.monotonic()
    deadline = started + 60
    async with httpx.AsyncClient(timeout=2) as client:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                health = (await client.get(f"http://127.0.0.1:{port}/healthz")).json()
            except (httpx.HTTPError, ValueError):
                await asyncio.sleep(0.5)
                continue
            if health.get("realtime", {}).get("state") == "verified":
                return time.monotonic() - started
            await asyncio.sleep(0.5)
    tail = _sanitized_log(log_path, settings)[-2000:]
    pytest.fail(f"app did not reach realtime 'verified' (exit={proc.poll()}). Log tail:\n{tail}")


async def _get_page(port: int, session_id: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10) as client:
        return await client.get(f"http://127.0.0.1:{port}/s/{session_id}")


async def test_server_restart_shows_cards_added_while_down(
    integration_settings, supabase_client, created_session_ids, tmp_path
):
    repo = Repository(supabase_client)
    service = SessionService(repo)
    session_id = new_session_id()
    await repo.create_session("IT restart " + secrets.token_hex(4), session_id)
    created_session_ids.append(session_id)
    view = await service.get(session_id)
    assert view is not None
    quadrant_id = next(q.id for q in view.quadrants if q.kind == "IS")
    text_a = "Before restart " + secrets.token_hex(4)
    text_b = "While down " + secrets.token_hex(4)
    await service.add_card(view.workspace_id, quadrant_id, text_a, author="Ann")

    repo_root = Path(__file__).resolve().parents[2]
    boot_seconds: list[float] = []
    logs: list[Path] = []
    for run in (1, 2):
        port = _free_port()
        log_path = tmp_path / f"app{run}.log"
        logs.append(log_path)
        with log_path.open("wb") as log_file:
            proc = subprocess.Popen(
                [sys.executable, "-m", "app"],
                cwd=repo_root,
                env={**os.environ, "APP_PORT": str(port), "REALTIME_CHECK": "strict"},
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            try:
                boot_seconds.append(
                    await _wait_verified(proc, port, log_path, integration_settings)
                )
                page = await _get_page(port, session_id)
                assert page.status_code == 200
                assert text_a in page.text
                if run == 1:
                    assert text_b not in page.text
                else:
                    assert text_b in page.text, "card written while the server was down is missing"
            finally:
                _stop(proc)
        if run == 1:
            # No server runs now: this write can only reach the second process via its page read.
            await service.add_card(view.workspace_id, quadrant_id, text_b, author="Bob")

    print(
        f"\nRESTART: boot to realtime verified: run 1 {boot_seconds[0]:.1f} s, "
        f"run 2 {boot_seconds[1]:.1f} s"
    )
    secrets_ = (
        integration_settings.supabase_secret_key.get_secret_value(),
        integration_settings.realtime_key(),
    )
    for log_path in logs:
        log_text = log_path.read_text(errors="replace")
        leaked = any(secret in log_text for secret in secrets_) or "apikey=" in log_text
        # Assert on a boolean: a failing `secret not in text` would print the text itself.
        assert not leaked, (
            f"key material in {log_path.name}:\n"
            + _sanitized_log(log_path, integration_settings)[-2000:]
        )
