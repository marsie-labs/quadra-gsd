"""Shared fixtures. Integration fixtures need a .env pointing at the hosted Supabase project."""

import pytest

import app.deps
from app.db.repository import Repository, connect
from app.deps import Services
from app.realtime.hub import RealtimeHub
from app.services.sessions import SessionService
from app.settings import Settings


@pytest.fixture(autouse=True)
def reset_services():
    yield
    app.deps.services = None


@pytest.fixture
def integration_settings() -> Settings:
    try:
        return Settings()
    except Exception:
        pytest.skip(
            "integration: .env with SUPABASE_URL, SUPABASE_SECRET_KEY, STORAGE_SECRET required"
        )


@pytest.fixture
async def supabase_client(integration_settings):
    client = await connect(integration_settings)
    yield client
    await client.postgrest.aclose()


@pytest.fixture
async def real_services(supabase_client, integration_settings) -> Services:
    # This hub is never started, so the Phase 1 e2e tests keep working without Realtime.
    hub = RealtimeHub(integration_settings.supabase_url, integration_settings.realtime_key())
    return Services(sessions=SessionService(Repository(supabase_client)), hub=hub)


@pytest.fixture
async def live_services(supabase_client, integration_settings):
    """Real services whose hub is started and strict-verified: CDC flows before a test writes."""
    repo = Repository(supabase_client)
    hub = RealtimeHub(integration_settings.supabase_url, integration_settings.realtime_key())
    await hub.run_startup_check("strict", repo.upsert_probe, timeout=20)
    try:
        yield Services(sessions=SessionService(repo), hub=hub)
    finally:
        await hub.stop()


@pytest.fixture
async def created_session_ids(supabase_client):
    ids: list[str] = []
    yield ids
    if ids:
        # quadrants (and cards) cascade with the workspace row
        await supabase_client.table("workspaces").delete().in_("session_id", ids).execute()
