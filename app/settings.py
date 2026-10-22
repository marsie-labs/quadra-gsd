"""Typed environment configuration.

Secrets are ``SecretStr`` so ``repr()``/``str()`` of a Settings instance never reveal them.
Never log or print a Settings instance anyway.
"""

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

STORAGE_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str
    # Server-side only: this key bypasses RLS and must never reach a browser.
    supabase_secret_key: SecretStr
    # Optional legacy service_role JWT, used only for Realtime if it rejects sb_secret_ keys.
    supabase_realtime_key: SecretStr | None = None
    # Signs the NiceGUI session cookie. Changing it re-prompts every browser for its name.
    storage_secret: SecretStr
    app_base_url: str = "http://localhost:8080"
    app_host: str = "127.0.0.1"
    app_port: int = 8080
    realtime_check: Literal["strict", "warn", "off"] = "strict"

    @field_validator("storage_secret")
    @classmethod
    def _storage_secret_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < STORAGE_SECRET_MIN_LENGTH:
            raise ValueError(
                "STORAGE_SECRET must be at least 32 characters (generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))")'
            )
        return value

    def realtime_key(self) -> str:
        """Key for the Realtime connection: the legacy override if set, else the secret key."""
        if self.supabase_realtime_key is not None:
            return self.supabase_realtime_key.get_secret_value()
        return self.supabase_secret_key.get_secret_value()
