"""Live proof that the public (publishable) key cannot reach the data: link-only access is
enforced by the database, not by hiding the keys. Needs SUPABASE_PUBLISHABLE_KEY in .env."""

import pytest
from postgrest.exceptions import APIError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.tokens import new_session_id
from supabase import AsyncClient, acreate_client

pytestmark = pytest.mark.integration


class AnonKeys(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str
    supabase_publishable_key: str | None = None


@pytest.fixture
async def anon_client():
    try:
        keys = AnonKeys()
    except Exception:
        pytest.skip("SUPABASE_URL not set")
    if not keys.supabase_publishable_key:
        pytest.skip("SUPABASE_PUBLISHABLE_KEY not set")
    client: AsyncClient = await acreate_client(keys.supabase_url, keys.supabase_publishable_key)
    yield client
    await client.postgrest.aclose()


async def test_publishable_key_cannot_call_create_session(anon_client):
    with pytest.raises(APIError) as denied:
        await anon_client.rpc(
            "create_session",
            {"p_project_name": "anon attempt", "p_session_id": new_session_id()},
        ).execute()
    assert denied.value.code == "42501"


async def test_publishable_key_cannot_read_workspaces(anon_client):
    with pytest.raises(APIError) as denied:
        await anon_client.table("workspaces").select("session_id").limit(1).execute()
    assert denied.value.code == "42501"
