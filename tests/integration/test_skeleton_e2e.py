"""End-to-end tracer proof against the hosted Supabase project."""

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
