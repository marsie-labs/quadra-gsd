---
phase: "03"
slug: "card-editing"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-23"
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser -> NiceGUI server | Untrusted draft text and key/blur/click events enter the editor handlers; menu clicks trigger delete, move and reorder. Card and quadrant ids come from server-side closures, never from the browser | Card text (user content, non-sensitive) |
| NiceGUI server -> Supabase PostgREST | The server writes with the secret key; every update, soft delete, move and order write is scoped by card id, workspace id and `deleted_at is null` | Card rows |
| Realtime hub -> CanvasView | Remote rows (any writer) arrive while a participant edits; they must not corrupt the open draft or the projection | Card rows |
| Any writer -> Supabase cards | SQL editor or scripts bypass Python validation; only DB constraints, the composite FK and the `cards_touch` trigger apply | Card rows |
| Developer CLI -> hosted Supabase | The migration push changes the shared hosted schema | DDL |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-03-SC | Tampering | dependency installs | high | mitigate | No packages installed; `pyproject.toml` and `uv.lock` unchanged since 4bb8c2f (git diff clean) | closed |
| T-03-01 | Tampering | edit of a card in another session | medium | mitigate | `Repository.update_card_text` filters by `workspace_id` and `deleted_at is null`; empty result raises `CardGone`; `test_edit_card_service_scoping` (hosted) | closed |
| T-03-02 | Tampering | `updated_at` rewound by a writer or race | medium | mitigate | `cards_touch` sets `greatest(pg_catalog.clock_timestamp(), old.updated_at + interval '1 microsecond')`; `test_writer_cannot_rewind_or_forge_timestamps` (hosted) | closed |
| T-03-03 | Repudiation | forged or cleared "(edited)" marker | low | mitigate | Trigger owns `text_updated_at` on UPDATE (`is distinct from old.text`); same hosted test | closed |
| T-03-04 | Tampering (XSS) | edited text rendered as markup | medium | mitigate | Text rendered only as `ui.label` / textarea value; no `ui.html`/`ui.markdown` under `app/ui`; UI test shows `<b>x</b>` literally | closed |
| T-03-05 | Denial of Service | oversized or blank edited text | low | mitigate | `validate_card_text` in UI and in `SessionService.edit_card`; DB CHECK `char_length(btrim(text)) between 1 and 500` | closed |
| T-03-06 | Tampering | schema drift repo vs hosted DB | medium | mitigate | Append-only migration 20261023120000; pushed migrations unchanged (git diff); dry run and `supabase migration list` Local/Remote evidence in 03-01-SUMMARY.md | closed |
| T-03-07 | Information Disclosure | write errors leaking details | low | mitigate | `_write` logs operation and exception class only; users see fixed messages (`EDIT_FAILED`, `CARD_GONE`) | closed |
| T-03-08 | Tampering | duplicate writes from Enter + blur / double Enter | low | mitigate | Edit session popped before first await; per-card `_busy` guard; disabled menu button; double-Enter and Enter-then-blur tests | closed |
| T-03-09 | Repudiation | anyone on the link edits any card without a name | low | accept | D-05 + link-based access model (see Accepted Risks) | closed |
| T-03-10 | Tampering (XSS) | card text in menu button accessible name | low | mitigate | `aria-label` set by props item assignment (never the props string parser), cut to 40 code points (`canvas_view.py:262`, `:346`) | closed |
| T-03-11 | Tampering | moving a card into another session's quadrant | medium | mitigate | `move_card` filters by `workspace_id`; composite FK `(quadrant_id, workspace_id)` rejects with 23503; `test_move_into_another_sessions_quadrant_is_rejected` (hosted) | closed |
| T-03-12 | Tampering | card data lost through hard delete | medium | mitigate | No `.delete(` in `app/db/repository.py`; delete sets `deleted_at`; live test proves row stays | closed |
| T-03-13 | Repudiation | anyone deletes any card with no confirmation | low | accept | D-08 + D-05 under link-based access (see Accepted Risks) | closed |
| T-03-14 | Tampering | duplicate writes from repeated menu clicks | low | mitigate | Per-card `_busy` guard + disabled menu button; `test_two_delete_clicks_before_the_write_returns_write_once`, `test_two_move_clicks_before_the_write_returns_write_once` | closed |
| T-03-15 | Denial of Service | write storm from renumbering on reorder | medium | mitigate | `reorder_card` writes only the moved card's `order_index`; `test_reorder_writes_exactly_one_row` (hosted) | closed |
| T-03-16 | Tampering | reordering a card of another session | low | mitigate | `get_card` and `set_card_order` filter by `workspace_id` and `deleted_at is null`; `CardGone` otherwise | closed |
| T-03-17 | Tampering (integrity) | concurrent reorders leaving clients in different orders | medium | mitigate | One sort key `(order_index, created_at, id)` for UI, `list_cards` and agent; `test_concurrent_reorders_converge` (hosted) | closed |
| T-03-18 | Tampering (integrity) | response for a deleted card resurrecting it / failed write leaving unconfirmed text | medium | mitigate | `_write` catches `CardGone`, removes the card and warns; other failures drop the optimistic row and re-render the last server row; CardGone and rollback UI tests | closed |
| T-03-19 | Tampering (integrity) | fake repository drifting from the real trigger | low | mitigate | `FakeRepository._touch` mirrors both trigger rules; the same rules proven against hosted Supabase in `test_card_edit_storage.py` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-09 | Anyone with the link may edit any card without a name (D-05). Link-based access with no auth is a project constraint (PROJECT.md); the creator stays the shown author and every change reaches all participants live | User decision D-05 (03-CONTEXT.md), recorded at plan time | 2026-10-23 |
| AR-03-02 | T-03-13 | Anyone with the link may delete any card without confirmation (D-08, D-05). Deletes are soft (`deleted_at`), so a deletion is recoverable in the database | User decisions D-08, D-05 (03-CONTEXT.md), recorded at plan time | 2026-10-23 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-23 | 20 | 20 | 0 | /gsd-secure-phase 03 (orchestrator, L1 grep-depth; register authored at plan time) |

Notes: Code review findings WR-01..WR-05 (03-REVIEW.md) are integrity/UX defects, not threats in this register; they remain `open` in 03-REVIEW-DISPOSITION.md for triage.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-23
