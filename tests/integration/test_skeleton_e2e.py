"""End-to-end tracer proof against the hosted Supabase project."""

import base64
import secrets

import pytest

import app.deps
from app.db.repository import Repository

LABELS = {"IS": "IS", "IS_NOT": "IS NOT", "DOES": "DOES", "DOES_NOT": "DOES NOT"}


@pytest.mark.integration
async def test_open_link_renders_canvas(user, real_services, supabase_client, created_session_ids):
    app.deps.services = real_services
    name = "Tracer open " + secrets.token_hex(4)
    sid = secrets.token_urlsafe(16)
    repo = Repository(supabase_client)

    await repo.create_session(name, sid)
    created_session_ids.append(sid)

    row = await repo.get_session(sid)
    assert row is not None
    quadrants = sorted(row["quadrants"], key=lambda q: q["position"])
    assert [(q["kind"], q["position"]) for q in quadrants] == [
        ("IS", 1),
        ("IS_NOT", 2),
        ("DOES", 3),
        ("DOES_NOT", 4),
    ]

    await user.open(f"/s/{sid}")
    await user.should_see(name)
    for kind, label in LABELS.items():
        user.find(marker=f"quadrant-{kind}")
        await user.should_see(label)


@pytest.mark.integration
async def test_unknown_session_returns_404(user, real_services):
    app.deps.services = real_services
    r = await user.http_client.get("/s/" + secrets.token_urlsafe(16))
    assert r.status_code == 404
    assert "Session not found" in r.text


@pytest.mark.integration
async def test_create_from_home_lands_on_canvas(
    user, real_services, supabase_client, created_session_ids
):
    app.deps.services = real_services
    name = "Tracer " + secrets.token_hex(4)

    await user.open("/")
    user.find("Project name").type(name)
    user.find("Create").click()

    # The Project name input still holds `name` on the home page, so waiting on the text alone
    # would pass before navigation. Wait for the canvas markers, which only exist on /s/{token}.
    await user.should_see(marker="project-name", content=name, retries=50)
    for kind, label in LABELS.items():
        await user.should_see(marker=f"quadrant-{kind}")
        await user.should_see(label)

    resp = await (
        supabase_client.table("workspaces")
        .select("id, session_id")
        .eq("project_name", name)
        .execute()
    )
    assert len(resp.data) == 1
    sid = resp.data[0]["session_id"]
    created_session_ids.append(sid)

    # Imported here so a missing app.tokens fails this assertion path, not collection.
    from app.tokens import SESSION_ID_RE

    assert SESSION_ID_RE.match(sid)
    assert len(sid) == 22
    assert len(base64.urlsafe_b64decode(sid + "==")) == 16

    quadrants = await (
        supabase_client.table("quadrants")
        .select("id")
        .eq("workspace_id", resp.data[0]["id"])
        .execute()
    )
    assert len(quadrants.data) == 4
