"""Live proof (hosted Supabase) of atomic creation and DB-side validation of create_session."""

import secrets

import pytest
from postgrest.exceptions import APIError

from app.db.repository import Repository
from app.tokens import new_session_id

pytestmark = pytest.mark.integration


def _marker() -> str:
    return "IT " + secrets.token_hex(4)


async def test_create_session_creates_open_session_with_four_quadrants(
    supabase_client, created_session_ids
):
    repo = Repository(supabase_client)
    marker = _marker()
    sid = new_session_id()

    returned = await repo.create_session(f"  {marker}  ", sid)
    created_session_ids.append(sid)

    assert returned == sid
    row = await repo.get_session(sid)
    assert row is not None
    assert row["status"] == "open"
    assert row["project_name"] == marker  # surrounding spaces trimmed by the RPC (btrim)
    assert len(row["quadrants"]) == 4
    assert {q["kind"] for q in row["quadrants"]} == {"IS", "IS_NOT", "DOES", "DOES_NOT"}
    assert {q["position"] for q in row["quadrants"]} == {1, 2, 3, 4}


async def test_failed_create_leaves_no_rows(supabase_client):
    marker = _marker()

    with pytest.raises(APIError) as bad_token:
        await supabase_client.rpc(
            "create_session", {"p_project_name": marker, "p_session_id": "short"}
        ).execute()
    assert bad_token.value.code == "23514"
    by_name = await (
        supabase_client.table("workspaces").select("id").eq("project_name", marker).execute()
    )
    assert by_name.data == []

    fresh = new_session_id()
    with pytest.raises(APIError) as blank_name:
        await supabase_client.rpc(
            "create_session", {"p_project_name": "   ", "p_session_id": fresh}
        ).execute()
    assert blank_name.value.code == "23514"
    by_token = await (
        supabase_client.table("workspaces").select("id").eq("session_id", fresh).execute()
    )
    assert by_token.data == []
    # Quadrants have a NOT NULL FK to workspaces and are inserted in the same function call, so
    # zero workspace rows means the failed call left no partial quadrant rows either.


async def test_duplicate_token_raises_23505(supabase_client, created_session_ids):
    repo = Repository(supabase_client)
    sid = new_session_id()
    await repo.create_session(_marker(), sid)
    created_session_ids.append(sid)

    with pytest.raises(APIError) as dup:
        await repo.create_session(_marker(), sid)
    assert dup.value.code == "23505"


async def test_same_name_twice_gives_two_sessions(real_services, created_session_ids):
    service = real_services.sessions
    name = _marker()

    first = await service.create_session(name)
    created_session_ids.append(first)
    second = await service.create_session(name)
    created_session_ids.append(second)

    assert first != second
    for sid in (first, second):
        view = await service.get(sid)
        assert view is not None
        assert view.project_name == name


async def test_project_name_length_parity_in_code_points(supabase_client, created_session_ids):
    repo = Repository(supabase_client)

    sid = new_session_id()
    await repo.create_session("é" * 100, sid)
    created_session_ids.append(sid)
    row = await repo.get_session(sid)
    assert row is not None
    assert row["project_name"] == "é" * 100

    with pytest.raises(APIError) as too_long:
        await repo.create_session("é" * 101, new_session_id())
    assert too_long.value.code == "23514"
