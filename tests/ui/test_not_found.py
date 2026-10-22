"""SESS-05: malformed and unknown links both give the same 404 page."""

from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, install_fake_services


async def test_malformed_id_returns_404_without_db_call(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    response = await user.http_client.get("/s/nope")
    assert response.status_code == 404
    assert "Session not found" in response.text
    assert "Create a new session" in response.text
    assert repo.get_calls == 0


async def test_unknown_well_formed_id_returns_404(user):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    response = await user.http_client.get("/s/" + "Q" * 22)
    assert response.status_code == 404
    assert "Session not found" in response.text
    assert "Create a new session" in response.text
    assert repo.get_calls == 1
