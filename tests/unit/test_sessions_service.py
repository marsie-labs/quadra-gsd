"""SessionService behavior on a FakeRepository: validation parity, retry, link pre-filter."""

import pytest
from postgrest.exceptions import APIError

from app.deps import get_services
from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, FakeRepository, install_fake_services


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   ", None),
        (None, None),
        ("  Acme  ", "Acme"),
        ("a" * 100, "a" * 100),
        ("a" * 101, None),
        ("é" * 100, "é" * 100),
        ("é" * 101, None),
    ],
    ids=["empty", "blank", "none", "trimmed", "100", "101", "100-multibyte", "101-multibyte"],
)
def test_validate_project_name(raw, expected):
    from app.services.sessions import validate_project_name

    assert validate_project_name(raw) == expected


def _service(repo: FakeRepository):
    from app.services.sessions import SessionService

    return SessionService(repo)  # type: ignore[arg-type]


async def test_create_session_rejects_blank_name_without_repository_call():
    from app.services.sessions import InvalidProjectName

    repo = FakeRepository()
    with pytest.raises(InvalidProjectName):
        await _service(repo).create_session("   ")
    assert repo.create_calls == 0


async def test_same_name_twice_gives_two_distinct_openable_sessions():
    repo = FakeRepository()
    service = _service(repo)
    first = await service.create_session("Acme")
    second = await service.create_session("Acme")
    assert first != second
    for sid in (first, second):
        view = await service.get(sid)
        assert view is not None
        assert view.project_name == "Acme"
        assert view.status == "open"


async def test_collision_is_retried_once_with_a_fresh_token():
    repo = FakeRepository()
    repo.fail_next_create_codes = ["23505"]
    sid = await _service(repo).create_session("Acme")
    assert repo.create_calls == 2
    assert sid in repo.rows


async def test_second_collision_propagates():
    repo = FakeRepository()
    repo.fail_next_create_codes = ["23505", "23505"]
    with pytest.raises(APIError) as exc:
        await _service(repo).create_session("Acme")
    assert exc.value.code == "23505"
    assert repo.create_calls == 2


async def test_non_collision_error_is_not_retried():
    repo = FakeRepository()
    repo.fail_next_create_codes = ["23514"]
    with pytest.raises(APIError) as exc:
        await _service(repo).create_session("Acme")
    assert exc.value.code == "23514"
    assert repo.create_calls == 1


@pytest.mark.parametrize(
    "bad_id", ["nope", "a" * 65, "bad!chars_____________"], ids=["short", "too-long", "bad-chars"]
)
async def test_get_prefilters_malformed_ids_without_repository_call(bad_id):
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    assert await get_services().sessions.get(bad_id) is None
    assert repo.get_calls == 0


async def test_get_unknown_well_formed_id_asks_the_repository():
    repo = FakeRepository()
    assert await _service(repo).get("Z" * 22) is None
    assert repo.get_calls == 1


async def test_get_returns_quadrants_in_position_order():
    repo = install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})
    view = await get_services().sessions.get(SEEDED_ID_A)
    assert view is not None
    assert [q.position for q in view.quadrants] == [1, 2, 3, 4]
    assert [q.kind for q in view.quadrants] == ["IS", "IS_NOT", "DOES", "DOES_NOT"]
    assert repo.get_calls == 1
