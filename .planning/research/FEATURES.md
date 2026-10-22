# Feature Research

**Domain:** Realtime collaborative workshop canvas ("IS / IS NOT / DOES / DOES NOT" boundary exercise) with agent export
**Researched:** 2026-10-22
**Confidence:** MEDIUM-HIGH (patterns from collaborative whiteboard tools — Miro, FigJam, EasyRetro, Parabol, Metro Retro — applied to a narrow 4-quadrant format)

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Create session from project name → shareable link | Every retro/board tool starts here | LOW | Unguessable `session_id` in URL is the access token; show "copy link" button |
| Join via link, enter display name once | No-account tools (EasyRetro, Metro Retro) do this | LOW | NiceGUI `app.storage.user` / `browser` remembers name; allow changing it |
| Four fixed, labeled quadrants with short guidance text | Core of the exercise; users need prompts ("What it IS…") | LOW | Fixed set, fixed order; seeded per session |
| Add text card to a quadrant | Core action | LOW | Enter-to-submit, empty-text rejected, sensible max length |
| Edit card text | Fixing typos is constant | LOW | Inline edit; last-write-wins at this scale |
| Delete card | Core action | LOW | Soft-delete in DB; disappears for everyone |
| Move card to another quadrant | Core of "boundary" debates (IS vs IS NOT) | LOW-MEDIUM | Move menu/buttons per user decision |
| Reorder cards within a quadrant | Users rank/group | MEDIUM | Up/down buttons fit "no drag-and-drop" decision; fractional order index |
| Live updates for all participants (< ~1s) | Defining property of the product | MEDIUM-HIGH | Supabase Realtime → server hub → NiceGUI clients |
| Card shows author + time | Accountability in workshops; explicit requirement | LOW | Display name + relative time |
| Explicit "Finish / Close Session" with confirmation | Irreversible action needs guard | LOW | Confirm dialog states "cannot be reopened" |
| Read-only state after close, visible to everyone | Users must know edits are no longer possible | LOW | Banner "Session closed at …"; controls hidden/disabled; server rejects writes |
| Machine-readable export of closed session | The agent hand-off is the product's purpose | LOW-MEDIUM | REST JSON, grouped by quadrant, stable schema |
| Connection status / auto-reconnect | Realtime tools must recover from Wi-Fi blips | MEDIUM | NiceGUI reconnects socket; server must resync state on reconnect |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Agent-ready structured export with explicit open/closed semantics | Most whiteboards export images/CSV; Quadra hands a locked, typed dataset to an AI harness | LOW | 409 while open is a clear contract; versioned JSON schema |
| Presence ("3 people here") | Social signal in live workshops | LOW-MEDIUM | NiceGUI knows connected clients per session in-process — cheap |
| Card count per quadrant | Quick balance check (empty IS NOT = weak boundaries) | LOW | Derived in UI |
| Facilitator prompts/examples per quadrant | Helps first-time teams | LOW | Static copy |
| "Closed by X at T" provenance in export | Trust in snapshot | LOW | Store `closed_by` display name |
| Markdown/clipboard export for humans | Useful outside agent flow | LOW | v1.x |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Drag-and-drop free canvas | "Feels like Miro" | Hard in server-driven UI under latency; ordering races; explicitly deferred | Move menu + up/down buttons |
| Accounts / roles / facilitator auth | "Security" | Slows teams; explicitly out of scope | Unguessable link; one-way close |
| Reopen closed session | "Forgot one card" | Breaks agent's stable-snapshot guarantee | Start new session (optionally "duplicate as new" later) |
| Real-time collaborative text editing within a card (CRDT) | Google-Docs feel | Huge complexity for one-line cards | Last-write-wins edits; cards are small |
| Voting / dot-voting, timers, grouping, comments | Retro tool feature creep | Not in intents; dilutes v1 | Defer to v2 if users ask |
| Undo history UI | Nice | Needs op log + conflict handling | Soft-delete retains data; restore later if needed |
| Agent push/webhook on close | "Automatic" | Adds outbound integration + retries; harness pulls on demand per intent | Agent polls GET endpoint; 409 until closed |
| MCP tool | Agent ergonomics | Explicitly REST-only for v1 | Thin FastMCP wrapper later over same service function |

## Feature Dependencies

```
Supabase schema (workspaces, quadrants, cards) + DB lock triggers
    └──requires──> Session creation (RPC: workspace + 4 quadrants)
                       └──requires──> Session page (render quadrants, display name)
                                          └──requires──> Realtime hub (subscription + fan-out + resync)
                                                             └──requires──> Card operations (add/edit/delete/move/reorder)
Session close (status open→closed, one-way)
    ├──requires──> Session page + Realtime hub (lock propagates live)
    └──enables──> Agent results endpoint (200 only when closed)

Optimistic UI ──enhances──> Card operations (needs dedupe of own Realtime echo)
Presence ──enhances──> Session page (needs hub's per-session client registry)
Reopen ──conflicts──> Agent stable snapshot
Drag-and-drop ──conflicts──> server-driven UI simplicity (v1)
```

### Dependency Notes

- **Card ops require the Realtime hub:** without fan-out, card ops only update the acting client; build hub before/with card ops so every op is tested multi-client.
- **Agent endpoint requires close semantics:** 409 vs 200 depends on status; endpoint reads DB, never in-memory UI state.
- **Optimistic UI requires echo dedupe:** acting client sees its change instantly, then receives the same change from Realtime; must reconcile by card id + `updated_at`/version.
- **Lock must be DB-enforced:** UI hiding controls isn't enough — a stale client or direct API call could still write.

## MVP Definition

### Launch With (v1)

- [ ] Create session → unique link — entry point
- [ ] Display name on join — author identity
- [ ] Four quadrants rendered with live card lists — core canvas
- [ ] Add / edit / soft-delete / move / reorder cards — core interaction
- [ ] Realtime sync across all clients via Supabase Realtime, with reconnect resync — core value
- [ ] Close session with confirmation, live lock for all clients, DB-enforced — snapshot integrity
- [ ] `GET /api/sessions/{session_id}/results` with 404 / 409 / 200 — agent hand-off
- [ ] Automated tests: DB rules, hub fan-out, UI (NiceGUI user fixture), endpoint, multi-client realtime integration — "done" bar

### Add After Validation (v1.x)

- [ ] Presence indicator — when sessions regularly have 4+ people
- [ ] Copy-link / QR button polish, quadrant guidance copy — first user feedback
- [ ] Markdown export for humans — if teams paste results into docs
- [ ] FastMCP wrapper over results service — if harness moves to MCP

### Future Consideration (v2+)

- [ ] Drag-and-drop — needs client-side component
- [ ] Voting / grouping / timers — retro-style facilitation
- [ ] Duplicate closed session into new open session — replaces "reopen"
- [ ] Deployment (container host), multi-instance scaling — when leaving local dev

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Session create + link | HIGH | LOW | P1 |
| Display name on join | HIGH | LOW | P1 |
| Card add/edit/delete | HIGH | LOW | P1 |
| Card move between quadrants | HIGH | LOW | P1 |
| Card reorder within quadrant | MEDIUM | MEDIUM | P1 |
| Realtime sync + reconnect resync | HIGH | HIGH | P1 |
| Close + DB-enforced lock | HIGH | MEDIUM | P1 |
| Agent results endpoint | HIGH | LOW | P1 |
| Optimistic UI | MEDIUM | MEDIUM | P1 (explicit requirement) |
| Presence | MEDIUM | LOW | P2 |
| Markdown export | LOW | LOW | P3 |

## Competitor Feature Analysis

| Feature | Miro/FigJam | EasyRetro/Metro Retro | Our Approach |
|---------|-------------|----------------------|--------------|
| Access | Accounts + share links | Link + optional name | Link + display name only |
| Canvas | Free-form infinite | Fixed columns | Fixed 4 quadrants |
| Card move | Drag | Drag | Move menu + up/down |
| End of session | None (board persists) | "Lock board"/hide | One-way close, read-only |
| Export | Image/PDF/CSV | CSV/PDF | Typed JSON for AI agent, gated on closed |

## Sources

- Product knowledge of Miro, FigJam, EasyRetro, Parabol, Metro Retro feature sets (MEDIUM — not re-verified this session)
- PROJECT.md decisions (move menu, no reopen, REST-only, exclude deleted) (HIGH)
- Supabase Realtime and NiceGUI docs (see STACK.md) for complexity estimates (HIGH)

---
*Feature research for: realtime collaborative boundary canvas*
*Researched: 2026-10-22*
