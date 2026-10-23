"""In-memory stand-in for the Repository, so service and UI tests run without Supabase.

``install_fake_services`` wires the REAL ``SessionService`` over ``FakeRepository``, so the
validation, retry and pre-filter logic under test is production code; only PostgREST is faked.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from postgrest.exceptions import APIError

import app.deps
from app.deps import Services
from app.realtime.hub import RealtimeHub
from app.services.sessions import SessionService
from app.tokens import SESSION_ID_RE

SEEDED_ID_A = "SeededSessionAaaaaaaaa"
SEEDED_ID_B = "SeededSessionBbbbbbbbb"
SEEDED_NAME_A = "Seeded Project A"
SEEDED_NAME_B = "Seeded Project B"

_KINDS = ("IS", "IS_NOT", "DOES", "DOES_NOT")


class FakeRepository:
    """Mimics ``Repository`` including the DB CHECK constraints and unique session_id.

    ``create_gate`` (an unset ``asyncio.Event``) holds a create in flight for the
    double-trigger tests; ``insert_gate`` does the same for a card insert. The
    ``fail_next_*_codes`` lists make the next call raise an ``APIError`` with that code.
    ``list_gate`` holds a card read AFTER its rows are computed, so a held read returns a
    snapshot older than whatever happens meanwhile; ``list_calls`` counts card reads.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.create_calls = 0
        self.get_calls = 0
        self.fail_next_create_codes: list[str] = []
        self.create_gate: asyncio.Event | None = None
        self.cards: dict[str, dict[str, Any]] = {}
        self.insert_calls = 0
        self.insert_gate: asyncio.Event | None = None
        self.fail_next_insert_codes: list[str] = []
        self.list_calls = 0
        self.list_gate: asyncio.Event | None = None
        self.fail_next_list_codes: list[str] = []
        self.fail_next_get_codes: list[str] = []

    async def create_session(self, project_name: str, session_id: str) -> str:
        self.create_calls += 1
        if self.create_gate is not None:
            await self.create_gate.wait()
        if self.fail_next_create_codes:
            code = self.fail_next_create_codes.pop(0)
            raise APIError({"code": code, "message": "injected"})
        name = project_name.strip()
        if not SESSION_ID_RE.fullmatch(session_id) or not 1 <= len(name) <= 100:
            raise APIError({"code": "23514", "message": "check constraint violated"})
        if session_id in self.rows:
            raise APIError({"code": "23505", "message": "duplicate session_id"})
        self.rows[session_id] = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "project_name": name,
            "status": "open",
            "quadrants": [
                {"id": str(uuid.uuid4()), "kind": kind, "position": position}
                for position, kind in enumerate(_KINDS, start=1)
            ],
        }
        return session_id

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        self.get_calls += 1
        if self.fail_next_get_codes:
            code = self.fail_next_get_codes.pop(0)
            raise APIError({"code": code, "message": "injected"})
        row = self.rows.get(session_id)
        if row is None:
            return None
        return {**row, "quadrants": [dict(q) for q in row["quadrants"]]}

    async def insert_card(
        self,
        *,
        workspace_id: str,
        quadrant_id: str,
        text: str,
        author: str,
        order_index: float,
    ) -> dict[str, Any]:
        """Mirror the cards constraints: composite FK, text 1-500 (btrim spaces), author 1-40."""
        self.insert_calls += 1
        if self.insert_gate is not None:
            await self.insert_gate.wait()
        if self.fail_next_insert_codes:
            code = self.fail_next_insert_codes.pop(0)
            raise APIError({"code": code, "message": "injected"})
        owned = any(
            row["id"] == workspace_id and any(q["id"] == quadrant_id for q in row["quadrants"])
            for row in self.rows.values()
        )
        if not owned:
            raise APIError({"code": "23503", "message": "foreign key violation"})
        if not 1 <= len(text.strip(" ")) <= 500 or not 1 <= len(author) <= 40:
            raise APIError({"code": "23514", "message": "check constraint violated"})
        now = datetime.now(UTC).isoformat()
        row = {
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "quadrant_id": quadrant_id,
            "text": text,
            "order_index": order_index,
            "author": author,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self.cards[row["id"]] = row
        return dict(row)

    async def list_cards(self, workspace_id: str) -> list[dict[str, Any]]:
        """Live cards of a workspace in (order_index, created_at, id) order."""
        self.list_calls += 1
        if self.fail_next_list_codes:
            code = self.fail_next_list_codes.pop(0)
            raise APIError({"code": code, "message": "injected"})
        rows = [
            dict(c)
            for c in self.cards.values()
            if c["workspace_id"] == workspace_id and c["deleted_at"] is None
        ]
        snapshot = sorted(rows, key=lambda c: (c["order_index"], c["created_at"], c["id"]))
        if self.list_gate is not None:
            await self.list_gate.wait()  # rows were computed first: a held read goes stale
        return snapshot

    async def max_order_index(self, quadrant_id: str) -> float | None:
        values = [
            c["order_index"]
            for c in self.cards.values()
            if c["quadrant_id"] == quadrant_id and c["deleted_at"] is None
        ]
        return max(values) if values else None


def install_fake_services(seed: dict[str, str] | None = None) -> FakeRepository:
    """Seed ``{session_id: project_name}`` rows and install a real service over the fake."""
    repo = FakeRepository()
    for session_id, project_name in (seed or {}).items():
        repo.rows[session_id] = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "project_name": project_name,
            "status": "open",
            "quadrants": [
                {"id": str(uuid.uuid4()), "kind": kind, "position": position}
                for position, kind in enumerate(_KINDS, start=1)
            ],
        }
    # The hub is never started and needs no network.
    hub = RealtimeHub("https://example.supabase.co", "sb_secret_FAKE_FOR_UI_TESTS")
    app.deps.services = Services(sessions=SessionService(repo), hub=hub)  # type: ignore[arg-type]
    return repo


def seed_card(
    repo: FakeRepository,
    session_id: str,
    kind: str,
    text: str,
    author: str = "Ann",
    order_index: float = 1024.0,
    created_at: str | None = None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    """Store a card straight into the fake (no service, no event) and return a copy of its row."""
    workspace = repo.rows[session_id]
    quadrant = next(q for q in workspace["quadrants"] if q["kind"] == kind)
    moment = created_at or datetime.now(UTC).isoformat()
    row = {
        "id": str(uuid.uuid4()),
        "workspace_id": workspace["id"],
        "quadrant_id": quadrant["id"],
        "text": text,
        "order_index": order_index,
        "author": author,
        "created_at": moment,
        "updated_at": moment,
        "deleted_at": deleted_at,
    }
    repo.cards[row["id"]] = row
    return dict(row)


def soft_delete_card(repo: FakeRepository, card_id: str) -> None:
    """Set ``deleted_at`` on a stored card without any service call or event."""
    repo.cards[card_id]["deleted_at"] = datetime.now(UTC).isoformat()


def card_event(
    row: dict[str, Any], event_type: str = "INSERT", old: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A Realtime postgres_changes payload for the cards table, as the hub callback receives it."""
    return {
        "ids": [],
        "data": {
            "schema": "public",
            "table": "cards",
            "type": event_type,
            "commit_timestamp": datetime.now(UTC).isoformat(),
            "errors": None,
            "record": row or {},
            "old_record": old or {},
        },
    }
