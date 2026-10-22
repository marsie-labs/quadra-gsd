# Architecture Research

**Domain:** Realtime collaborative workshop canvas — single Python process (FastAPI + NiceGUI) relaying Supabase Realtime to browsers
**Researched:** 2026-10-22
**Confidence:** HIGH for component boundaries; MEDIUM for Realtime reconnect specifics (validate in implementation)

## Standard Architecture

### System Overview

```
 Browsers (participants)                       External agent harness
   |  NiceGUI socket.io (UI diffs, events)        |  HTTPS GET /api/sessions/{id}/results
   v                                              v
+---------------------------- Python process (uvicorn, 1 worker) ----------------------------+
|  NiceGUI pages            FastAPI routes                                                    |
|  /            (create)    /api/sessions/{id}/results  (404 / 409 / 200)                    |
|  /s/{session_id} (canvas) /healthz                                                          |
|        |                        |                                                           |
|        v                        v                                                           |
|  SessionService  (create, add/edit/delete/move/reorder card, close, get_results)            |
|        |                                                                                    |
|        v                                                                                    |
|  Repository (supabase AsyncClient: table ops + .rpc())                                      |
|                                                                                             |
|  RealtimeHub  <-- on_postgres_changes(cards, workspaces) -- one AsyncRealtime channel       |
|     registry: session_id -> {connected NiceGUI clients / canvas views}                      |
|     dispatch: change -> views for that session -> update UI in each client's context        |
+---------------------------------------------------------------------------------------------+
        |  PostgREST (HTTPS)                         ^  Realtime WebSocket (CDC)
        v                                            |
+---------------------------- Supabase (hosted) ---------------------------------------------+
|  workspaces(id, session_id, project_name, status, created_at, closed_at, closed_by)         |
|  quadrants(id, workspace_id, kind IS|IS_NOT|DOES|DOES_NOT, position)                        |
|  cards(id, workspace_id, quadrant_id, text, order_index, author, created_at, updated_at,    |
|        deleted_at)                                                                          |
|  RPC: create_session(project_name), close_session(session_id, closed_by)                    |
|  Triggers: reject card writes when workspace closed; forbid closed -> open; touch updated_at|
|  Publication: supabase_realtime includes cards, workspaces                                  |
|  RLS: enabled, no anon/authenticated policies (server uses secret key)                      |
+---------------------------------------------------------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Schema + migrations | Tables, enums, constraints, triggers, RPCs, publication, RLS | `supabase/migrations/*.sql`, applied with Supabase CLI |
| Repository | Only place that talks to Supabase PostgREST; maps rows ↔ Pydantic models | `AsyncClient.table(...)`, `.rpc(...)` |
| SessionService | Business rules + validation (text length, open-session checks for UX), orchestrates repository | Plain async class; shared by UI and REST |
| RealtimeHub | Owns the Realtime connection; subscribes once at startup; keeps session→views registry; dispatches changes; resyncs on reconnect | Started in `app.on_startup`, stopped on shutdown |
| Canvas page (NiceGUI) | Renders quadrants + cards for one session; registers with hub on connect, unregisters on disconnect; applies optimistic updates | `@ui.page('/s/{session_id}')`, `ui.refreshable` per quadrant |
| Create page | Project name form → `create_session` → redirect to `/s/{session_id}` | `@ui.page('/')` |
| Results API | Agent contract: 404 unknown, 409 open, 200 closed with typed JSON | FastAPI router + Pydantic response model |
| Settings | Env config | pydantic-settings |

## Recommended Project Structure

```
quadra/
├── app/
│   ├── main.py              # FastAPI app, ui.run_with(app), startup/shutdown wiring
│   ├── settings.py          # pydantic-settings
│   ├── models.py            # Pydantic: Workspace, Quadrant, Card, SessionResults
│   ├── db/
│   │   ├── client.py        # acreate_client factory (async)
│   │   └── repository.py    # CRUD + rpc calls
│   ├── services/
│   │   └── sessions.py      # SessionService
│   ├── realtime/
│   │   └── hub.py           # RealtimeHub: subscribe, registry, dispatch, resync
│   ├── ui/
│   │   ├── create_page.py   # '/'
│   │   ├── canvas_page.py   # '/s/{session_id}'
│   │   └── components.py    # quadrant column, card widget, move menu
│   └── api/
│       └── results.py       # GET /api/sessions/{session_id}/results
├── supabase/
│   └── migrations/          # SQL schema, triggers, RPCs, publication
├── tests/
│   ├── unit/                # services, models, hub dispatch with fake events
│   ├── ui/                  # NiceGUI user-fixture tests
│   ├── api/                 # results endpoint via httpx ASGITransport
│   └── integration/         # real Supabase: triggers, RPCs, realtime round-trip (marked)
├── pyproject.toml
└── .env.example
```

### Structure Rationale

- **db/ vs services/:** UI and REST share one service layer, so the agent export and canvas can never disagree on rules.
- **realtime/ isolated:** the riskiest component; testable with fake change events, swappable (Postgres Changes → Broadcast) without touching UI.
- **supabase/migrations:** DB-level guarantees (lock, one-way status) are part of the product, so they live in version control and get integration tests.

## Architectural Patterns

### Pattern 1: Single server subscription + in-process fan-out (hub)

**What:** One Realtime channel subscribed to `cards` and `workspaces` (`on_postgres_changes("*", schema="public", table=...)`). Each change carries `workspace_id`; the hub routes it to every registered view for that session.
**When to use:** Server-driven UI, single process, small scale.
**Trade-offs:** + one connection to manage, one reconnect path, no per-session channel lifecycle. − all changes flow through one process (fine at 2–10 users/session); multi-process would need Redis/pub-sub.

**Example:**
```python
class RealtimeHub:
    def __init__(self, client: AsyncClient):
        self._client = client
        self._views: dict[str, set[CanvasView]] = defaultdict(set)

    async def start(self) -> None:
        channel = self._client.channel("quadra-db")
        channel.on_postgres_changes("*", schema="public", table="cards", callback=self._on_change)
        channel.on_postgres_changes("UPDATE", schema="public", table="workspaces", callback=self._on_change)
        await channel.subscribe(self._on_status)

    def _on_change(self, payload) -> None:
        record = payload["data"]["record"]          # verify exact payload shape in Phase 1
        for view in list(self._views.get(record["workspace_id"], ())):
            view.apply_change(payload)              # runs in that client's UI context
```

### Pattern 2: DB as source of truth; optimistic UI with echo reconciliation

**What:** Acting client updates its own UI immediately, writes via service, then receives the Realtime echo. Views keep `card_id -> updated_at`; an echo with `updated_at <=` current local value is ignored. Failed writes roll back the local change and notify.
**When to use:** Explicit requirement for smooth UX under light latency.
**Trade-offs:** + snappy UX. − must handle echo/duplicate and failure rollback; last-write-wins on concurrent edits.

### Pattern 3: Invariants enforced in Postgres

**What:** `BEFORE INSERT/UPDATE` trigger on `cards` raises if parent workspace `status = 'closed'`; trigger on `workspaces` forbids `closed -> open`; `close_session` RPC does `UPDATE ... WHERE status = 'open'` (idempotent, race-safe); `create_session` RPC inserts workspace + 4 quadrants in one transaction.
**When to use:** Any rule the agent relies on (immutable snapshot).
**Trade-offs:** + impossible to violate from any client. − logic split between SQL and Python; needs integration tests against real DB.

### Pattern 4: Resync on (re)connect

**What:** Realtime does not replay missed events. When a NiceGUI client (re)connects, or the hub's channel re-subscribes, reload full session state from DB and re-render.
**Trade-offs:** + correctness after Wi-Fi blips / server restarts. − one extra query per reconnect (trivial at this scale).

## Data Flow

### Card mutation

```
User clicks "Add" in browser A
    -> NiceGUI event (socket.io) -> canvas view A: optimistic render
    -> SessionService.add_card -> Repository insert (PostgREST) -> Postgres
    -> trigger checks workspace open; row committed
    -> Realtime CDC event -> RealtimeHub._on_change
    -> views for session (A, B, C): A reconciles echo, B/C render new card
    -> NiceGUI pushes UI diff to each browser
```

### Close session

```
User confirms "Finish" -> SessionService.close -> rpc close_session (WHERE status='open')
    -> workspaces UPDATE event -> hub -> all views switch to read-only + banner
    -> any later card write -> trigger raises -> service maps to "session closed" message
```

### Agent fetch

```
GET /api/sessions/{id}/results -> SessionService.get_results
    -> workspace not found -> 404
    -> status open -> 409 {"detail": "Session is still open"}
    -> status closed -> query quadrants + cards (deleted_at IS NULL, ordered) -> 200 JSON
```

### Key Data Flows

1. **Identity:** display name stored per browser in `app.storage.user` (requires `storage_secret`); written into `cards.author` and `workspaces.closed_by`.
2. **Ordering:** `order_index double precision`; insert at end = max + 1024; move between neighbours = midpoint; occasional renormalize if gaps collapse.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| v1: 2–10 users/session, few sessions | Single process, single Realtime channel, Postgres Changes — fine |
| Dozens of concurrent sessions | Filter subscriptions per session or move to Broadcast from Database; still single process |
| Multi-instance deployment | NiceGUI needs sticky sessions; hub per instance each subscribed to Realtime works (every instance sees all changes) — that's an advantage of DB-driven fan-out |

### Scaling Priorities

1. **First bottleneck:** NiceGUI per-client server memory/CPU with many tabs — measure before optimizing.
2. **Second bottleneck:** Postgres Changes single-thread throughput — switch to Broadcast from Database.

## Anti-Patterns

### Anti-Pattern 1: Broadcasting in-process and skipping Realtime

**What people do:** Since the server performs all writes, push updates to other clients directly and never subscribe to the DB.
**Why it's wrong:** Violates requirement ("via Supabase Realtime events"); misses writes made outside the app (SQL editor, scripts, future second instance).
**Do this instead:** Write to DB; let Realtime be the single fan-out trigger (optimistic local render only for the actor).

### Anti-Pattern 2: Lock enforced only in UI

**What people do:** Hide buttons when closed.
**Why it's wrong:** Stale tabs, slow Realtime, or direct calls still write; agent snapshot becomes non-deterministic.
**Do this instead:** DB trigger + service check + UI disable.

### Anti-Pattern 3: Agent endpoint reading in-memory UI state

**What people do:** Serialize hub/view state.
**Why it's wrong:** Empty after restart; may include unconfirmed optimistic changes.
**Do this instead:** Query DB in `get_results`.

### Anti-Pattern 4: Updating NiceGUI elements outside a client context / from another thread

**What people do:** Call UI updates directly from Realtime callback without client context.
**Why it's wrong:** NiceGUI needs updates on its event loop in the right client's context; elements may belong to disconnected clients.
**Do this instead:** Keep hub on the same asyncio loop (start in `app.on_startup`); dispatch with `with view.client:`; skip/unregister disconnected clients (`client.on_disconnect`).

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Supabase PostgREST | supabase-py `AsyncClient` table ops + `.rpc()` | Use secret key server-side; map PostgREST errors (trigger `RAISE`) to domain errors |
| Supabase Realtime | `on_postgres_changes` on one channel | Tables must be in `supabase_realtime` publication; consider `REPLICA IDENTITY FULL` on cards to get old quadrant on moves; verify secret-key auth |
| Agent harness | REST GET, JSON | Stable, versioned response schema (`schema_version: 1`) |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| UI ↔ SessionService | Direct async calls | UI never touches repository |
| REST ↔ SessionService | Direct async calls | Same rules as UI |
| RealtimeHub ↔ Canvas views | Register/unregister + `apply_change` | Hub knows nothing about widgets |
| SessionService ↔ Repository | Async methods returning Pydantic models | Repository is the only Supabase importer besides hub |

## Sources

- https://supabase.com/docs/guides/realtime/postgres-changes — publication, replica identity, RLS, single-thread ordering, throughput
- realtime-py README — channel API, filters, `replication_ready`
- https://supabase.com/docs/reference/python/realtime-api — async-only client
- https://nicegui.io/documentation/section_configuration_deployment — background tasks + client context, storage
- https://nicegui.io/documentation/storage — `app.storage.user/browser/client` scopes
- https://supabase.com/blog/realtime-broadcast-from-database — scaling alternative

---
*Architecture research for: realtime collaborative boundary canvas*
*Researched: 2026-10-22*
