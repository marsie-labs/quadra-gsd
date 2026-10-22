# Phase 1: Session Skeleton - Context

**Gathered:** 2026-10-22
**Status:** Ready for planning

<domain>
## Phase Boundary

A user creates a session by entering a project name and lands on `/s/<session_id>` (≥128-bit random token). Anyone with the link — no login — opens the same session, sees the four labeled quadrants (IS, IS NOT, DOES, DOES NOT, empty in this phase), and is asked for a display name that the browser remembers. Unknown `session_id` shows a not-found page. Underneath: uv project, settings, FastAPI + NiceGUI single-worker app, Supabase migrations (schema for sessions/quadrants/cards, atomic `create_session`, publication), README setup, and a startup check proving DB change events reach the Python server.

Card add/edit/delete/move, live card sync, close, and the agent API belong to Phases 2–5.

</domain>

<decisions>
## Implementation Decisions

### Display name prompt
- **D-01:** First-time visitor sees an **inline banner** on the canvas page asking for a display name — NOT a blocking modal and NOT a separate join screen. The canvas (quadrants) is fully visible and usable behind it; the visitor may ignore the banner.
- **D-02:** Every card must have a real author. When an unnamed participant attempts an authoring action (adding a card, Phase 2), the app prompts for the name at that moment and completes the action only after a valid name is given. Phase 1 must expose a reusable "ensure display name, then continue" helper so Phase 2 can call it; no "Anonymous" fallback author exists.
- **D-03:** Display name is **fixed per browser** once set — no rename UI. Changing it requires clearing browser storage. The current name is shown on the canvas page (e.g., header) as read-only text. Name persists across reloads and across different sessions in the same browser (IDEN-02).
- **D-04:** Name rules: whitespace trimmed; empty after trim is rejected; max 40 characters; duplicate names across participants are allowed (no auth by design). Invalid input shows an inline validation message, nothing is saved.

### Claude's Discretion
User chose not to discuss these; planner/researcher pick sensible defaults consistent with research docs:
- **Canvas layout & header** — 2×2 quadrant grid arrangement, header content (project name, current display name), empty-quadrant appearance. Copy-link button is v2 (UX-04) — not required here.
- **Home page** — project name form + create button; project name validation (required, trimmed, sensible max length) at Claude's discretion.
- **Not-found page** — friendly message for unknown `session_id`; a link back to home is reasonable.
- **Startup Realtime check** — behavior on failure (fail fast vs. warn), reporting channel (log and/or `/healthz`). Must make it obvious to a developer whether DB change events reach the server (success criterion 5).
- **Token format** — `session_id` generation (e.g., `secrets.token_urlsafe(16)` or UUIDv4), separate internal PK per research.
- **Name storage mechanism** — research recommends NiceGUI `app.storage.user` with `storage_secret`; any per-browser mechanism meeting D-03 is acceptable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope & requirements
- `.planning/ROADMAP.md` §Phase 1 — goal, success criteria 1–5, requirement IDs
- `.planning/REQUIREMENTS.md` — SESS-01..05, IDEN-01..03, QUAL-04 definitions
- `.planning/PROJECT.md` — constraints (Python end-to-end, no polling, link-based access, DB-level integrity), key decisions

### Technical research
- `.planning/research/SUMMARY.md` — stack, architecture, phase implications, open gaps (sb_secret_ key vs legacy JWT for Realtime)
- `.planning/research/STACK.md` — pinned versions, async-only Realtime client, single uvicorn worker
- `.planning/research/ARCHITECTURE.md` — component layout, schema sketch, `create_session` RPC, RealtimeHub, page routes
- `.planning/research/PITFALLS.md` — Realtime silent failure, guessable ids, `storage_secret` requirement
- `.planning/research/FEATURES.md` — table-stakes UX for create/join

### Project instructions
- `.claude/CLAUDE.md` — stack table, "What NOT to use", GSD workflow rules

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield repo. Only `supabase/.temp/` exists (Supabase CLI linked to hosted project ref `fligjsqzjoyedcuolwss`); `supabase init` / `supabase/config.toml` not yet created.

### Established Patterns
- None yet; this phase establishes project layout, settings, migrations, and test patterns for later phases.

### Integration Points
- Hosted Supabase project (existing, CLI linked). `supabase/.temp/` should be gitignored (STATE.md note).

</code_context>

<specifics>
## Specific Ideas

- Name prompt should be non-intrusive (banner), but authorship must never be missing — prompt lazily at first authoring action.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-session-skeleton*
*Context gathered: 2026-10-22*
