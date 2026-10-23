# Phase 02 (live-shared-canvas) UI Review

**Audited:** 2026-10-23
**Baseline:** Abstract 6-pillar standards (no 02-UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server running; code-only audit)
**Interaction captures:** off (`interaction_capture: false`)

## Pillar Scores

| Pillar | Score | Key Finding |
|---|---|---|
| 1. Copywriting | 3/4 | Specific, plain-language messages, but the over-length error reads "Card text is required", and there are two different name prompts ("Save" banner vs "Continue" dialog) |
| 2. Visuals | 3/4 | Clear 2x2 quadrant hierarchy (h5 project name, h6 quadrant labels), but cards are unstyled, nothing distinguishes quadrants, and the card column has no height bound |
| 3. Color | 2/4 | No declared palette; Quasar defaults. `text-grey` (#9E9E9E on white, about 2.7:1) is used for the "No cards yet" hint, the author/time meta line and the header display name, below WCAG AA 4.5:1 for small text |
| 4. Typography | 3/4 | Five Quasar tokens in use (h4 on home only, h5, h6, caption, body); no explicit weights. Caption meta line is 0.75rem grey and hard to read |
| 5. Spacing | 3/4 | Only standard tokens (`gap-4`, `gap-2`, `items-center`, `w-full`), no arbitrary values. Quadrant columns have no max height, so a long session grows the grid without bound |
| 6. Experience Design | 2/4 | Good empty, error, double-submit and name-gate handling, but no loading state on page open and no browser-visible indication when Realtime is reconnecting, so a stale canvas looks live |

**Overall: 16/24**

No pillar scored 1 and no defect prevents the core task (adding a card, seeing it appear). No BLOCKER raised; all findings are WARNINGs.

## Top 3 Priority Fixes

1. **No feedback while loading or while live sync is down.** A participant can see a stale canvas that looks live, and first paint waits on two database reads with nothing shown. Fix: in `app/ui/canvas_page.py`, render the header and a `ui.spinner` (or "Loading cards...") before awaiting `sessions.get` and `list_cards`, then swap in the grid. Add a visible banner driven from hub state (`reconnecting` → "Live updates paused, reconnecting...") that clears on `verified`; needs a small per-client status hook from the hub to open canvases.

2. **Secondary text fails WCAG AA contrast.** The "No cards yet" hint, each card's "author · HH:MM" line and the header display name are hard to read. Fix: in `app/ui/canvas_view.py:78` and `:154`, and `app/ui/canvas_page.py:62`, replace `text-grey` with a darker token (e.g. `text-grey-8`, about #616161, roughly 5.9:1 on white) or set a project palette with `ui.colors(...)` in `app/main.py`.

3. **Over-length error says the wrong thing.** Pasting 501 characters shows "Card text is required (max 500 characters)", implying the field was empty. Fix: in `app/services/sessions.py`, split `CARD_TEXT_ERROR` into "Card text is required" (empty/whitespace) and "Card text must be 500 characters or fewer" (over-length); have `validate_card_text` return the reason so `canvas_view.py:98` and `:106` pick the right message. Update `tests/ui/test_cards.py` and `tests/unit/test_card_rules.py`.

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Strengths: specific, actionable messages. "Could not add the card. Please try again." (`canvas_view.py:116`), "Could not refresh the cards. Reload the page to try again." (`canvas_view.py:243`), "Temporarily unavailable" plus "Could not load this session. Please reload in a moment." (`canvas_page.py:25-26`), "Pick a display name so teammates know who added what." (`identity.py:60`), "No cards yet" (`canvas_view.py:78`). No generic "Submit", "OK" or "Anonymous" strings under `app/ui`.
- WARNING: over-length case shows "Card text is required (max 500 characters)" (`canvas_view.py:98` and `:106` both use `CARD_TEXT_ERROR`). See Top Fix 3.
- WARNING: two name prompts ask the same thing with different CTAs: banner "Save" (`identity.py:73`) vs dialog "Enter your name to continue" / "Continue" (`identity.py:89`, `:102`). Consider one wording and one CTA.
- WARNING: add CTA is the bare verb "Add" (`canvas_view.py:86`), repeated four times, with identical field label "New card" (`canvas_view.py:83`). See Pillar 6 accessibility.
- Note: card meta line uses server local time (`canvas_view.py:33`, `format_card_time` with `tz=None`). Accepted decision (A-02); recorded as a UX caveat, not a defect.

### Pillar 2: Visuals (3/4)
- Strengths: clear focal hierarchy. Project name `text-h5` (`canvas_page.py:60`), quadrant labels `text-h6` (`canvas_view.py:73`), responsive grid `grid-cols-1 md:grid-cols-2` (`canvas_view.py:66`).
- WARNING: no visual differentiation of quadrants (no tint, border or icon); IS / IS NOT / DOES / DOES NOT distinguished only by heading.
- WARNING: card widgets (`canvas_view.py:151`) are plain `ui.card().classes("w-full")`, separated only by `gap-2`.
- No icon-only buttons; meta-line tooltip (`canvas_view.py:155`) is the only hover affordance.

### Pillar 3: Color (2/4)
- No project palette: no `ui.colors(...)`, custom CSS or `primary` override under `app/`. Primary-blue buttons for Add (x4), Save, Continue, Cancel and Create.
- `text-grey` appears 4 times (`canvas_view.py:78`, `canvas_view.py:154`, `canvas_page.py:62`, plus one `text-caption text-grey`). No hardcoded hex or `rgb(` under `app/ui`.
- WARNING (contrast): `text-grey` = #9E9E9E, about 2.7:1 on white, below WCAG AA 4.5:1; meta line is 0.75rem.
- WARNING (accent distribution): four identical blue Add buttons visible at once on desktop; no 60/30/10 split defined.
- Positive: error states use Quasar error color via `field.error` and `ui.notify(type="negative")`.

### Pillar 4: Typography (3/4)
- Sizes: `text-h4` (home title, `home_page.py:39`), `text-h5` (project name, 404/503 headings, `canvas_page.py:25`, `:40`, `:60`), `text-h6` (quadrant labels, `canvas_view.py:73`), `text-caption` (meta line, `canvas_view.py:153`), default body.
- No explicit `font-*` weights; hierarchy implicit from Quasar heading tokens.
- WARNING: card text is default body size; the grey caption meta line below it limits reading density on a dense canvas.

### Pillar 5: Spacing (3/4)
- Standard tokens only: `gap-4` grid (`canvas_view.py:66`), `gap-2` columns (`canvas_view.py:75`), `items-center w-full` rows (`canvas_view.py:80`, `canvas_page.py:59`). No arbitrary values.
- WARNING: quadrant column (`canvas_view.py:75`) has no `max-h` or scroll container; each card pushes the add field further down. Consider a fixed-height scroll region with the add field pinned.
- Add row relies on NiceGUI default gap; not verified in a browser.

### Pillar 6: Experience Design (2/4)
Covered states:
- Empty: "No cards yet" per quadrant via `_refresh_hint` (`canvas_view.py:261-263`).
- Validation: empty/whitespace text sets a field error, writes nothing (`canvas_view.py:97-98`); runs before the name gate.
- Double submit: per-quadrant in-flight set plus `button.disable()` (`canvas_view.py:100-101`), released in `finally` (`:136-137`).
- Failure: add failures notify and keep text (`canvas_view.py:115-116`); page-open DB failures return 503, never 404 (`canvas_page.py:21-26`, `:52-57`); resync failures keep cards and warn (`canvas_view.py:239-243`).
- Name gate: Cancel writes nothing and keeps text (`identity.py:101`, `canvas_view.py:102-103`).

Gaps:
- WARNING (loading): nothing renders until both reads complete (`canvas_page.py:33-57`), no spinner or skeleton; blank page up to `response_timeout=10` (`canvas_page.py:30`). See Top Fix 1.
- WARNING (live-status invisibility): hub `reconnecting` state exposed only at `/healthz`; a canvas that lost Realtime looks identical to a live one until resync.
- WARNING (accessibility): every quadrant's Add button and field share the same accessible name ("Add", "New card"). Fix: `ui.input(f"New card in {QUADRANT_LABELS[kind]}")` and `ui.button(f"Add to {QUADRANT_LABELS[kind]}")`.
- Destructive confirmation: not applicable (no delete UI this phase).
- Focus: field cleared after add (`canvas_view.py:126`) but focus not explicitly managed; not verified in a browser.

## Registry Safety
Not applicable: NiceGUI project with no `components.json`; no third-party blocks.

## Limitations
- No screenshots. Visual claims (spacing, rendered contrast, breakpoints at 375/768/1440 px, focus rings) are code-derived; 2.7:1 is computed from the Quasar grey-6 token.
- Interaction capture off; hover, focus and reconnect behavior unverified in a real browser by the auditor (covered separately by human UAT in 02-UAT.md, 6/6 passed).

## Files Audited
- `app/ui/canvas_view.py`
- `app/ui/canvas_page.py`
- `app/ui/identity.py`
- `app/ui/home_page.py`
- `app/ui/pages.py`
- `app/models.py` (QUADRANT_LABELS, lines 10-15)
- `app/main.py` (ui.run_with configuration; no theme or color override)
- Phase 2 artifacts: `02-01` to `02-05` PLAN.md and SUMMARY.md

Priority fixes: 3. Minor recommendations: 4 (quadrant visual differentiation, card styling, per-quadrant accessible names, time-zone caveat).
