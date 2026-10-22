"""Launcher and /healthz unit tests (no network, no NiceGUI globals touched)."""

import runpy
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from app.main import create_app, health_router


class StubHub:
    def __init__(self, state: str, stage: str | None = None, error: str | None = None) -> None:
        self._status = {
            "state": state,
            "stage": stage,
            "latency_ms": 12.0 if state == "verified" else None,
            "error": error,
        }

    def status(self) -> dict[str, Any]:
        return dict(self._status)


def _health_app(hub: object | None) -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    if hub is not None:
        app.state.hub = hub
    return app


async def _get_health(app: FastAPI) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/healthz")


def test_launcher_runs_uvicorn_once_with_one_worker(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("STORAGE_SECRET", "x" * 40)
    monkeypatch.setenv("APP_PORT", "8123")
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: calls.append((a, kw)))

    runpy.run_module("app", run_name="__main__")

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert (args[0] if args else kwargs.get("app")) is create_app
    assert kwargs["factory"] is True
    assert kwargs["workers"] == 1
    assert kwargs["port"] == 8123


async def test_healthz_verified_is_ok():
    resp = await _get_health(_health_app(StubHub("verified")))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["realtime"]["state"] == "verified"
    assert set(body["realtime"]) == {"state", "stage", "latency_ms", "error"}
    assert set(body) == {"status", "realtime"}


async def test_healthz_failed_is_degraded():
    resp = await _get_health(_health_app(StubHub("failed", stage="connect", error="HTTP 401")))
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "degraded"
    assert body["realtime"]["state"] == "failed"
    assert body["realtime"]["stage"] == "connect"


async def test_healthz_without_hub_is_pending_and_degraded():
    resp = await _get_health(_health_app(None))
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["realtime"] == {
        "state": "pending",
        "stage": None,
        "latency_ms": None,
        "error": None,
    }


async def test_healthz_disabled_is_ok():
    resp = await _get_health(_health_app(StubHub("disabled")))
    body = resp.json()
    assert body["status"] == "ok"
    assert body["realtime"]["state"] == "disabled"


@pytest.mark.parametrize("state", ["verified", "failed", "disabled", "pending"])
async def test_healthz_exposes_only_the_documented_keys(state):
    resp = await _get_health(_health_app(StubHub(state)))
    assert set(resp.json()["realtime"]) == {"state", "stage", "latency_ms", "error"}
