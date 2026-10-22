"""Shared fixtures. Integration fixtures need a .env pointing at the hosted Supabase project."""

import pytest

import app.deps
from app.db.repository import Repository, connect
from app.deps import Services
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
async def real_services(supabase_client) -> Services:
    return Services(sessions=SessionService(Repository(supabase_client)))


@pytest.fixture
async def created_session_ids(supabase_client):
    ids: list[str] = []
    yield ids
    if ids:
        # quadrants (and cards) cascade with the workspace row
        await supabase_client.table("workspaces").delete().in_("session_id", ids).execute()
