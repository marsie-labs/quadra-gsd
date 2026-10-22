"""Session link tokens. The token is the access capability, so it must be unguessable."""

import re
import secrets

# Mirrors the workspaces.session_id CHECK constraint in the init migration.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{22,64}$")


def new_session_id() -> str:
    """16 CSPRNG bytes -> 22-char URL-safe token (128 random bits; UUIDv4 has only 122)."""
    return secrets.token_urlsafe(16)
