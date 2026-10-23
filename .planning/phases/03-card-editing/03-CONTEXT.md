# Phase 3: Card Editing - Context

**Gathered:** 2026-10-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Participants can edit a card's text, soft-delete a card, move a card to another quadrant via a menu, and reorder a card up/down within its quadrant — all propagated live to every client on the session, and all feeling instant for the acting participant (optimistic, no duplicate/flicker on Realtime echo, rollback with a message on failure). Requirements: CARD-02, CARD-03, CARD-04, CARD-05, CARD-08.

Not in this phase: session close/lock (Phase 4), agent results API (Phase 5), drag-and-drop, co-editing inside a card, undo.

</domain>

<decisions>
## Implementation Decisions

### Edit interaction
- **D-01:** Editing is **inline in place**: the card's text label is swapped for a textarea inside the same card. No dialog. Edit validation reuses `validate_card_text` (trim, 1–500 code points) and the inline `field.error` pattern from the add input; error text is `CARD_TEXT_ERROR`.
- **D-02:** Edit starts from the card's ⋮ menu → "Edit" **and** by clicking the card text.
- **D-03:** Commit/cancel: **Enter saves, Shift+Enter inserts a newline, blur (click away) saves, Esc cancels** and restores the original text. If the trimmed text is unchanged, no write is made. Invalid text (empty/over-length) keeps the editor open with the inline error. Blur with invalid text does not save.
- **D-04:** Remote change during an edit: **keep the local draft, last save wins**. While a participant has the editor open, incoming Realtime updates for that card must not replace or destroy the textarea or the draft. (Today `_apply` deletes and rebuilds the card widget on every update, so the planner has to handle this.) On save, the draft overwrites the remote text (LWW). On cancel, the card shows the latest known server state, including the remote change. No "someone else changed this" hint.
- **D-05:** **Anyone on the link can edit, delete, move or reorder any card.** The shown author stays the original creator. No `edited_by` is stored. Edit/delete/move/reorder do **not** require a display name: Phase 1 D-02's name gate applies only to creating cards.
- **D-06:** Cards show an **"(edited)" marker** (next to the time in the meta line) **only after the card's text has changed**. Moving or reordering a card must not mark it edited. Planner picks the cheapest reliable signal (for example a `text_updated_at` column set by a trigger only when `text` changes, or an equivalent). The signal must be part of the card row so it reaches other clients through Realtime and survives reload. — **Reversibility:** costly — needs a forward migration on the hosted DB (new column and/or trigger), and the column then becomes part of the card row the Phase 5 agent snapshot reads.

### Card action controls
- **D-07:** Every card gets **one ⋮ overflow menu button** holding: **Edit**, **Move to →** (the three other quadrants, by label), **Move up**, **Move down**, **Delete**. Cards otherwise stay clean (text + meta line). Must work on touch, so no hover-only controls.
- **D-08:** **Delete is instant, with no confirmation dialog and no undo**: the card disappears optimistically and a short toast says "Card deleted". It is a soft delete (`deleted_at` set; the row is kept).
- **D-09:** **Move to another quadrant places the card at the end** of the target quadrant (same rule as add: target max visible `order_index` + `ORDER_GAP`).
- **D-10:** **Move up / Move down are shown but disabled** on the first/last card of a quadrant, so the menu shape stays stable. A single-card quadrant has both disabled.

### Claude's Discretion
User chose not to discuss these. Planner/researcher pick defaults consistent with prior decisions:
- **Reorder mechanics & concurrency:** how up/down computes the new `order_index` (for example the midpoint with the neighbor beyond the swap target, or the end ± gap at the edges; never renumber the quadrant, per CLAUDE.md), and what happens when two people reorder the same quadrant at once. The only requirement is that the order matches across clients and after reload (SC-4). Ties already resolve by `created_at`, then `id`.
- **Optimistic feedback & rollback (CARD-08):** whether a pending write is visually marked (none vs a subtle dim), and how rollback looks. It must restore the previous card state and show a `ui.notify` message in the existing style ("Could not … Please try again.", type negative). No duplicates or flicker when the echo arrives: the keyed upsert plus the `updated_at` stale guard must not let an optimistic local row block or duplicate the confirmed row.
- **Edge cases mid-edit:** card deleted or moved to another quadrant by someone else while the editor is open (a sensible default: on delete, close the editor and notify; on move, the planner decides).
- **`updated_at` maintenance:** there is currently **no trigger bumping `cards.updated_at`** on UPDATE. The Phase 2 stale guard (older ignored, equal applies) depends on it. The planner decides between a DB trigger (preferred: it also covers direct-DB edits, SYNC-03) and setting it from the service.
- **Write path:** PostgREST `update` vs an RPC per operation; per-operation validation in `SessionService` (text rules, quadrant belongs to the same workspace, which the composite FK already enforces).
- **Re-entrancy guards** per card (double Enter, double menu click), mirroring the `_adding` guard on add.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope & requirements
- `.planning/ROADMAP.md` §Phase 3 — goal, success criteria 1–5, requirement IDs
- `.planning/REQUIREMENTS.md` — CARD-02..05, CARD-08 definitions; Out of Scope (no drag-and-drop, no CRDT, last-write-wins)
- `.planning/PROJECT.md` — constraints and Key Decisions table (soft-delete, move via menu, snapshot + stale guard)

### Prior phase context
- `.planning/phases/01-session-skeleton/01-CONTEXT.md` — D-02 name gate (applies to card creation only; see D-05 here)
- `.planning/phases/02-live-shared-canvas/02-01-PLAN.md`, `02-03-SUMMARY.md`, `02-04-SUMMARY.md` — keyed upsert `apply_card`, stale `updated_at` guard, DELETE events carry only `old_record.id`, snapshot/buffer protocol
- `.planning/phases/02-live-shared-canvas/02-UI-REVIEW.md` — open UI warnings (`text-grey` contrast, identical accessible names); new menu items need distinct accessible names

### Technical research
- `.planning/research/ARCHITECTURE.md` — gapped double-precision ordering, RPC guidance, hub fan-out
- `.planning/research/PITFALLS.md` — Realtime/optimistic-echo pitfalls
- `.planning/research/FEATURES.md` — card editing UX expectations
- `.claude/CLAUDE.md` — stack, "What NOT to use" (no renumbering, no polling)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/ui/canvas_view.py` `CanvasView.apply_card` / `_apply`: already a full-row projection. It handles a quadrant change (removes the old widget, renders in the new list), a soft delete (`deleted_at` set → `_remove`) and sorted placement via `card_sort_key`. Move, reorder and delete echoes need no new projection logic. Edit needs an "editor open" exception (D-04).
- `CanvasView._remove`, `_refresh_hint`, `_notify`: reuse for optimistic delete and rollback messaging.
- `app/services/sessions.py`: `validate_card_text`, `CARD_TEXT_ERROR`, `InvalidCardText`, `ORDER_GAP`, `next_order_index` (D-09 move-to-end reuses it).
- `app/db/repository.py`: `CARD_COLUMNS`, `max_order_index(quadrant_id)`, `list_cards`. It is the only PostgREST access path, so new update methods go here.
- `QUADRANT_LABELS` in `app/models.py` for the "Move to →" submenu labels.

### Established Patterns
- Pages → `get_services().sessions` → `Repository`; the UI never touches the client directly.
- Error handling: catch, `logger.warning(type(exc).__name__)`, `ui.notify("Could not … Please try again.", type="negative")`.
- Re-entrancy guard set before the first await, released in `finally` (`_adding`).
- User text only via `ui.label` (never HTML/Markdown).
- Forward-only migrations; never edit pushed files (`20261022000000_init_schema.sql`, `20261023000000_author_nonblank.sql`).
- Test markers: `.mark("card", f"card-{id}")`, `card-text`, `card-meta`; NiceGUI `user` fixture for UI tests, integration tests against hosted Supabase.

### Integration Points
- `cards` table: `order_index double precision`, `updated_at` default now() (no update trigger), `deleted_at`; partial index on `(quadrant_id, order_index, created_at, id) where deleted_at is null`.
- RealtimeHub → `CanvasView.apply_card` / `remove_card` (already wired for UPDATE events).
- Phase 4 will add DB-level rejection of writes to closed sessions. Phase 3 write paths should surface DB errors through the same rollback + notify path, so Phase 4 only adds the message.

</code_context>

<specifics>
## Specific Ideas

- Sticky-note feel: click the text to edit in place, Enter to save, no extra buttons.
- Workshop speed over safety: instant delete with no confirmation (rows are soft-deleted anyway).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Undo-after-delete was considered and declined, not deferred.)

</deferred>

---

*Phase: 03-card-editing*
*Context gathered: 2026-10-23*
