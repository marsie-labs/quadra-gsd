# Pitfalls Research

**Domain:** Realtime collaborative canvas — NiceGUI + supabase-py Realtime + agent REST export
**Researched:** 2026-10-22
**Confidence:** HIGH for Supabase/NiceGUI documented caveats; MEDIUM for reconnect behaviour of realtime-py (verify empirically)

## Critical Pitfalls

### Pitfall 1: Using the sync Supabase client for Realtime

**What goes wrong:** Subscriptions silently never fire or raise; code copied from JS docs doesn't translate.
**Why it happens:** supabase-py has sync and async clients; Realtime works only with async.
**How to avoid:** Use `acreate_client` everywhere (one async client for PostgREST + Realtime), created in `app.on_startup` on NiceGUI's event loop.
**Warning signs:** No events in a manual SQL-update smoke test; "event loop" errors.
**Phase to address:** Phase 1 (foundation spike: insert row via SQL editor → Python callback prints).

---

### Pitfall 2: Tables not in the `supabase_realtime` publication / wrong key or role

**What goes wrong:** Subscription reports SUBSCRIBED but no change events arrive.
**Why it happens:** Postgres Changes only stream tables in the publication; events are filtered through RLS for the token's role; realtime client expects a JWT with `role`/`exp` — new `sb_secret_` keys may not behave like `service_role` JWT.
**How to avoid:** Migration adds `cards` and `workspaces` to the publication; enable RLS (deny-all for anon) and connect Realtime with a key whose role bypasses or satisfies RLS; test both key formats in Phase 1 and document which works.
**Warning signs:** SUBSCRIBED status but silence; events only for some tables.
**Phase to address:** Phase 1.

---

### Pitfall 3: Missed events after disconnect (no replay)

**What goes wrong:** After Wi-Fi blip, server restart, or Realtime channel drop, a client shows stale cards forever.
**Why it happens:** Realtime is fire-and-forget; NiceGUI reconnects the socket but doesn't know what it missed; realtime-py channel may need re-subscribe.
**How to avoid:** Full state reload from DB on every page (re)connect and whenever the hub's channel transitions back to SUBSCRIBED; log CHANNEL_ERROR/TIMED_OUT/CLOSED and resubscribe with backoff.
**Warning signs:** Two browsers disagree after one went offline briefly.
**Phase to address:** Realtime hub phase.

---

### Pitfall 4: UI updates from the wrong context / to dead clients

**What goes wrong:** Exceptions like "client has been deleted", updates applied to the wrong tab, memory leak as hub holds references to closed pages.
**Why it happens:** Realtime callback isn't in a NiceGUI client context; views never unregister.
**How to avoid:** Register view on page connect, unregister in `client.on_disconnect`; dispatch with `with view.client:`; guard against errors per view so one broken client doesn't stop fan-out to others.
**Warning signs:** Growing hub registry size; errors in logs after closing tabs.
**Phase to address:** Realtime hub phase.

---

### Pitfall 5: Optimistic update + Realtime echo = duplicate or flickering cards

**What goes wrong:** Acting user sees card twice, or edited text flickers back to old value.
**Why it happens:** Local optimistic render, then echo of own write (and possibly an older event arriving late).
**How to avoid:** Key cards by DB id (generate UUID client/server-side before insert so optimistic card and echo share id); compare `updated_at`; ignore older-or-equal; rollback + notify on write failure.
**Warning signs:** Duplicate cards in UI tests; edits revert under latency.
**Phase to address:** Card operations phase.

---

### Pitfall 6: Session lock only in UI; close races

**What goes wrong:** Card written after close (stale tab, concurrent click), so agent snapshot differs between fetches — breaks Core Value.
**Why it happens:** Close implemented as UI state + plain UPDATE without guards.
**How to avoid:** DB trigger rejects card INSERT/UPDATE when workspace closed; `close_session` RPC `UPDATE ... WHERE status='open'` (idempotent; second click is no-op); trigger forbids `closed → open`; service maps trigger error to friendly "session closed" message.
**Warning signs:** Integration test "write after close" passes the write.
**Phase to address:** Close phase (triggers can land in Phase 1 schema, tested in close phase).

---

### Pitfall 7: Guessable `session_id`

**What goes wrong:** Anyone can enumerate sessions and edit or read them (link = credential; agent endpoint has no auth).
**Why it happens:** Using sequential IDs or short slugs.
**How to avoid:** ≥128-bit random token (`secrets.token_urlsafe(16)` or UUIDv4) as public `session_id`; internal PK separate; don't list sessions anywhere.
**Warning signs:** IDs that look sequential or short.
**Phase to address:** Phase 1 schema / session creation.

---

### Pitfall 8: Order index collisions and renumber storms

**What goes wrong:** Concurrent reorders produce equal indices or jumping cards; moving one card rewrites every card in quadrant (N Realtime events).
**Why it happens:** Dense integer ordering.
**How to avoid:** Sparse/fractional `order_index` (gap 1024 / midpoint), tie-break by `created_at, id`; renormalize rarely.
**Warning signs:** Many UPDATE events per single move.
**Phase to address:** Card operations phase.

---

### Pitfall 9: Running multiple workers

**What goes wrong:** Users on different workers don't see each other's updates consistently; NiceGUI sessions break.
**Why it happens:** `uvicorn --workers N` or gunicorn default configs.
**How to avoid:** Single worker for v1; document in README and run script.
**Phase to address:** Phase 1.

---

### Pitfall 10: Tests that don't test realtime for real

**What goes wrong:** Unit tests pass with mocks; real multi-client sync broken.
**Why it happens:** Realtime needs a live Supabase; hard to test, so skipped.
**How to avoid:** Layered tests — (a) hub dispatch with fake payloads, (b) NiceGUI `user` fixture for UI flows, (c) marked integration tests against Supabase: write via repository → assert hub receives event within timeout → two simulated views converge. Use dedicated test data (unique project names) and cleanup, or local `supabase start`.
**Warning signs:** No test ever opens a real Realtime connection.
**Phase to address:** Every phase adds tests; final phase adds E2E multi-client test.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| One global Realtime channel for all sessions | Simple | Every event hits server regardless of session | v1 scale — acceptable |
| Postgres Changes instead of Broadcast | Less setup | Scaling ceiling | v1 — acceptable |
| Last-write-wins card edits | No conflict UI | Rare lost edit | Acceptable for one-line cards |
| Hosted dev project for integration tests | No Docker | Test data pollution, flakiness | Acceptable if tests clean up; switch to local stack if flaky |
| Skip RLS because server uses secret key | Faster | Anyone with publishable key could read all sessions | Never — enable RLS deny-all |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Supabase Realtime | Expecting old row on UPDATE | Set `REPLICA IDENTITY FULL` on `cards` if old quadrant needed for moves (or re-render both quadrants from new record) |
| Supabase Realtime | Relying on DELETE events | Soft-delete is an UPDATE (`deleted_at` set) — no DELETE semantics needed |
| PostgREST errors | Treating trigger `RAISE` as 500 | Use a known SQLSTATE/message; map to `SessionClosedError` |
| supabase-py `.rpc()` | Multi-step inserts from Python (workspace then 4 quadrants) non-atomic | One SQL function in a transaction |
| NiceGUI storage | `app.storage.user` without `storage_secret` | Pass `storage_secret` in `ui.run_with` |
| NiceGUI 3.x | Global-scope UI + page functions mixed | Page functions only |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-render whole canvas on every event | Flicker, lost input focus while typing | Refresh only affected quadrant(s); don't re-render card being edited | Noticeable with ~30+ cards |
| Unindexed `workspace_id` lookups | Slow resync | Index `cards(workspace_id)`, `workspaces(session_id)` unique | Grows with sessions |
| Resync storm on server restart | Burst of queries | Fine at v1 scale | Hundreds of clients |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Secret key in browser / committed `.env` | Full DB access | Server-only, `.env` gitignored, `.env.example` committed |
| RLS disabled | Publishable key reads everything | RLS on, no anon policies |
| Unbounded card text | Storage abuse, UI break | Max length (e.g., 500 chars) in DB `CHECK` + UI |
| Rendering card text as HTML | XSS across participants | Use plain-text NiceGUI elements (`ui.label`), never `ui.html` with user text |
| Display name spoofing | Low (no auth by design) | Accept; document |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Accidental close | Workshop ends, irreversible | Confirm dialog with explicit "can't be reopened" text |
| Silent write failure after close | Lost card text | Toast "Session was closed by X" and keep text visible to copy |
| No connection indicator | Users think they're synced when not | Show reconnecting state; resync after |
| Losing input when others' updates re-render | Frustration | Don't re-render the input/editing card |

## "Looks Done But Isn't" Checklist

- [ ] **Realtime sync:** works after browser reconnect and after server restart — verify with resync test
- [ ] **Close:** writes rejected at DB level — verify with direct repository insert after close
- [ ] **Close:** second close click is no-op, not error — verify idempotency
- [ ] **Agent export:** excludes soft-deleted cards, ordered by `order_index` — verify fixture with deleted + reordered cards
- [ ] **Agent export:** 404 unknown, 409 open (exact message "Session is still open"), 200 closed — verify all three
- [ ] **Move:** card disappears from old quadrant in *other* clients — verify multi-view test
- [ ] **Display name:** persists across reload and is used as author — verify UI test
- [ ] **Hub:** unregisters closed tabs — verify registry size returns to 0

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Realtime key/role mismatch | LOW | Switch Realtime auth key; config-only |
| Postgres Changes too slow | MEDIUM | Replace hub subscription with Broadcast-from-Database triggers; hub interface unchanged |
| Lock only in UI shipped | MEDIUM | Add trigger migration; audit closed sessions for late writes |
| Dense ordering shipped | LOW | Migration to double precision + renormalize |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Sync client / publication / key role (1, 2) | Phase 1 foundation | Integration smoke: SQL insert → Python callback within 5s |
| Guessable session_id (7) | Phase 1 / session creation | Test token length/entropy |
| Multiple workers (9) | Phase 1 | Run script uses single worker |
| Missed events / resync (3) | Realtime hub | Reconnect test reloads state |
| Wrong context / dead clients (4) | Realtime hub | Registry size test after disconnect |
| Echo duplicates (5), ordering (8) | Card operations | UI tests with simulated echo |
| Lock races (6) | Session close | Integration: write after close rejected; double close no-op |
| Fake realtime tests (10) | All; final E2E phase | Marked integration suite runs green against Supabase |

## Sources

- https://supabase.com/docs/guides/realtime/postgres-changes — publication, replica identity, DELETE/RLS caveats, single-thread
- https://supabase.com/docs/reference/python/realtime-api — async-only
- realtime-py README — JWT key requirement, subscribe states
- https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys.md — key formats
- https://nicegui.io/documentation/section_configuration_deployment, /storage, /section_testing
- General experience with collaborative realtime apps (optimistic UI, ordering) — MEDIUM

---
*Pitfalls research for: realtime collaborative boundary canvas*
*Researched: 2026-10-22*
