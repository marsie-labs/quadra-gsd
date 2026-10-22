"""Behavior tests for app.settings.Settings (env configuration, secret masking)."""

import pytest
from pydantic import ValidationError

from app.settings import Settings

SECRET_KEY = "sb_secret_UNITTESTVALUE"
STORAGE_SECRET = "s" * 32 + "UNITTESTSTORAGE"
REALTIME_JWT = "eyJ.UNITTESTREALTIMEJWT"

ENV_NAMES = [
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_REALTIME_KEY",
    "STORAGE_SECRET",
    "APP_BASE_URL",
    "APP_HOST",
    "APP_PORT",
    "REALTIME_CHECK",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from an empty settings environment."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", SECRET_KEY)
    monkeypatch.setenv("STORAGE_SECRET", STORAGE_SECRET)
    return monkeypatch


def make() -> Settings:
    # _env_file=None keeps a developer's real .env out of unit tests.
    return Settings(_env_file=None)


def test_loads_with_required_vars_and_applies_defaults(valid_env: pytest.MonkeyPatch) -> None:
    settings = make()

    assert settings.supabase_url == "https://example.supabase.co"
    assert settings.supabase_secret_key.get_secret_value() == SECRET_KEY
    assert settings.storage_secret.get_secret_value() == STORAGE_SECRET
    assert settings.realtime_check == "strict"
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8080
    assert settings.app_base_url == "http://localhost:8080"


def test_missing_storage_secret_is_rejected(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.delenv("STORAGE_SECRET")

    with pytest.raises(ValidationError):
        make()


def test_short_storage_secret_is_rejected(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("STORAGE_SECRET", "x" * 31)

    with pytest.raises(ValidationError, match="at least 32 characters"):
        make()


def test_missing_secret_key_is_rejected(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.delenv("SUPABASE_SECRET_KEY")

    with pytest.raises(ValidationError):
        make()


def test_unknown_realtime_check_mode_is_rejected(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("REALTIME_CHECK", "maybe")

    with pytest.raises(ValidationError):
        make()


@pytest.mark.parametrize("mode", ["strict", "warn", "off"])
def test_known_realtime_check_modes_are_accepted(valid_env: pytest.MonkeyPatch, mode: str) -> None:
    valid_env.setenv("REALTIME_CHECK", mode)

    assert make().realtime_check == mode


def test_realtime_key_falls_back_to_secret_key(valid_env: pytest.MonkeyPatch) -> None:
    assert make().realtime_key() == SECRET_KEY


def test_realtime_key_prefers_dedicated_override(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("SUPABASE_REALTIME_KEY", REALTIME_JWT)

    assert make().realtime_key() == REALTIME_JWT


def test_repr_and_str_never_reveal_secret_values(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("SUPABASE_REALTIME_KEY", REALTIME_JWT)
    settings = make()

    for rendered in (repr(settings), str(settings)):
        assert SECRET_KEY not in rendered
        assert STORAGE_SECRET not in rendered
        assert REALTIME_JWT not in rendered
