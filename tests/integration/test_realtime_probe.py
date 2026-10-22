"""Live proof (hosted Supabase) that a DB change event reaches the Python server via Realtime."""

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
