# Phase 1 — UI Review

**Audited:** 2026-10-22
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md). CONTEXT.md decisions D-01..D-04 used as the behavioural contract.
**Screenshots:** not captured (no dev server answered on localhost:8080, 3000 or 5173; code-only audit)
**Interaction captures:** off (workflow.ui_interaction_capture is false)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Specific, plain copy on the canvas and 404; validation messages disagree on wording and limit ("Required (max 100 characters)" vs "Name is required (max 40 characters)") |
| 2. Visuals | 2/4 | The four quadrants are visually identical cards, and the bare display name in the header is unlabelled and reads like a second title |
| 3. Color | 2/4 | No declared palette (Quasar defaults only); `text-grey` (#9E9E9E, about 2.7:1 on white) carries the display name and empty-state text, below WCAG AA |
| 4. Typography | 3/4 | Small, consistent set: text-h4, text-h5, text-h6 plus body; no explicit weights; no declared type scale |
| 5. Spacing | 3/4 | Only one explicit spacing class (`gap-4`); everything else relies on Quasar defaults; responsive grid breakpoint is sound |
| 6. Experience Design | 2/4 | Enter-key path bypasses the in-flight guard and can create duplicate sessions; canvas has no error handling for a failed session lookup |

**Overall: 15/24**

---

## Top 3 Priority Fixes

1. **Duplicate sessions possible via Enter key** — a user who presses Enter twice (or Enter then clicks Create) while the first create is in flight gets two sessions, because `create_button.disable()` only guards the button, not the `keydown.enter` handler — fix: in `app/ui/home_page.py`, add a local `busy` flag at the top of `create()` (`if busy: return`; set True; reset in `finally`), or set `name_input.disable()` alongside the button so neither path can re-enter.

2. **Canvas page crashes into a generic error on a failed lookup** — if `get_services().sessions.get()` raises (Supabase unreachable, timeout past `response_timeout=10`), the visitor gets NiceGUI's default error page with no recovery path, and a valid link looks broken — user impact: a transient outage reads as a dead session — fix: in `app/ui/canvas_page.py` wrap the `get` call in `try/except Exception`, log a warning, and render "Could not load this session" with a "Try again" action (`ui.navigate.reload`) and the home link.

3. **Display name and empty-state text fail contrast and are ambiguous** — `text-grey` (#9E9E9E, about 2.7:1 on white) is used for the header name (`canvas_page.py:24`) and "No cards yet" (`canvas_page.py:36`), and the bare name beside the project title has no label, so it reads as part of the title — fix: use `text-grey-7` (#616161, about 5.9:1) for both, and prefix the header name with a label such as "You: " or "Signed in as" so its role is explicit.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

**Strengths**
- Banner copy is task-specific: "Pick a display name so teammates know who added what." (`app/ui/identity.py:60`) explains why the name matters.
- 404 copy is plain and actionable: "Session not found" / "This link does not match any session." with "Create a new session" (`canvas_page.py:16-18`).
- No generic CTA labels ("Submit", "OK") in `app/ui`; grep for generic verbs returned only "Save", "Cancel" and "Continue" in the name dialog/banner, which are acceptable.
- No "Anonymous" fallback exists anywhere (D-02 honoured in copy).

**Findings**
- WARNING: Inconsistent validation copy. Home page uses `PROJECT_NAME_ERROR` = "Required (max 100 characters)" (`home_page.py:36`), while the identity flow uses `NAME_ERROR` = "Name is required (max 40 characters)" (`identity.py:18`). Same pattern, two phrasings, two limits. Align the phrasing ("Name is required (max N characters)") for both.
- WARNING: The home page has no explanatory copy. `home_page.py:33` shows the heading "Quadra" and then only a field and a "Create" button; a first-time visitor is not told what a session is or what happens next.
- INFO: The save button in the banner is labelled "Save" (`identity.py:72`). "Continue" (used in the dialog) or "Save name" would be more specific.
- INFO: Error toast "Could not create the session. Please try again." (`home_page.py:27`) is acceptable but does not say whether the name was kept; the input value is preserved, so this is fine in practice.

### Pillar 2: Visuals (2/4)

**Strengths**
- Clear reading order on the canvas: project name as `text-h5` first (`canvas_page.py:22`), then the banner, then the grid.
- Banner is inline and non-modal (D-01), so the canvas stays visible behind it.

**Findings**
- WARNING: The four quadrants are rendered by one identical code path (`canvas_page.py:33-36`) with identical card styling, a label and "No cards yet". Nothing signals the IS / IS NOT / DOES / DOES NOT distinction beyond the text, so the 2x2 boundary-canvas concept is not visually expressed. Add a per-quadrant accent or a short guiding question per quadrant as the layout gets fleshed out.
- WARNING: The header display name (`canvas_page.py:24`) is an unlabelled grey string sitting directly beside the `text-h5` project name. Without a label it reads as a subtitle or a second title, not "who I am".
- INFO: The 404 page is unstyled text (`canvas_page.py:16-18`): no card, no icon, no visual weight. Acceptable for a skeleton; flag for polish.
- INFO: No icon-only controls exist in this phase, so the icon-label pairing check does not apply.

### Pillar 3: Color (2/4)

**Strengths**
- No hard-coded hex or rgb values under `app/ui` (grep returned none).
- No accent-color classes (`text-primary`, `bg-primary`) are used, so there is no accent overuse.

**Findings**
- WARNING: `text-grey` (Quasar default #9E9E9E) is used on two information-bearing elements: the display name (`canvas_page.py:24`) and "No cards yet" (`canvas_page.py:36`). Contrast against white is about 2.7:1, below the WCAG AA threshold of 4.5:1 for body text. Use `text-grey-7` (#616161, about 5.9:1).
- WARNING: No palette or theme is declared anywhere in `app/ui` or in the NiceGUI setup. Every color is Quasar's default. Fine for a walking skeleton, but there is no 60/30/10 split to audit and no dark-mode decision recorded.
- INFO: The default Quasar primary (blue) is applied implicitly to the Create, Save and Continue buttons. Acceptable, but it is the only accent on the page, so it is the de facto brand color by default.

### Pillar 4: Typography (3/4)

**Strengths**
- Small, consistent heading scale: `text-h4` (home title, `home_page.py:33`), `text-h5` (project name and 404 title, `canvas_page.py:16,22`), `text-h6` (quadrant labels, `canvas_page.py:35`), and default body text.
- No font-family overrides and no ad-hoc sizes; no arbitrary `text-[...]` values.

**Findings**
- INFO: No font weights are set explicitly. Acceptable, but the quadrant labels (`text-h6`) and the project name (`text-h5`) are distinguished only by size.
- INFO: No declared type scale in the phase artifacts, so the chosen sizes cannot be checked against a contract.

Size distribution observed: 4 distinct text classes (h4, h5, h6, body) plus `text-grey` as a color modifier. Within the 4-size guideline.

### Pillar 5: Spacing (3/4)

**Strengths**
- The one explicit spacing rule is responsive: `grid-cols-1 md:grid-cols-2 gap-4 w-full` (`canvas_page.py:32`) collapses to one column below Quasar's md breakpoint, so mobile (375px) gets a single stack of quadrants.
- `items-center` on the header row keeps the title and the display name aligned (`canvas_page.py:21`).

**Findings**
- WARNING: Spacing is almost entirely Quasar default. There are no padding or margin classes on the home form, the banner or the 404 block; the gap between the banner card and the grid is whatever Quasar's default column spacing produces. Set an explicit vertical rhythm (for example `gap-4` on the outer column) so it is intentional.
- INFO: Only one spacing token (`gap-4`) is used across all of `app/ui`. Consistent, but too few tokens to judge a scale.
- INFO: Tablet (768px) renders the grid as a single column because 768 < Quasar's md breakpoint (1024px). Acceptable, but this was not visually verified (no screenshots).

Spacing class counts: `gap-4` x1; `items-center` x1; `w-full` x2. No arbitrary values.

### Pillar 6: Experience Design (2/4)

**Strengths**
- Empty state exists: "No cards yet" in each quadrant (`canvas_page.py:36`).
- Unknown and malformed links return a real HTTP 404 with a link back to `/` (`canvas_page.py:15-18`), per SESS-05.
- Inline name validation with no save on invalid input, for both the home form (`home_page.py:17`) and the banner (`identity.py:65-67`).
- Create failures are caught and surfaced with `ui.notify` (`home_page.py:25-27`), and the button is re-enabled in `finally` (`home_page.py:29-30`).
- Two-browser, no-login access is covered by tests (SESS-04).

**Findings**
- BLOCKER-level defect (scored as WARNING under the rubric, because the task still completes): the in-flight guard does not cover the Enter key. `name_input.on("keydown.enter", create)` (`home_page.py:38`) calls the same `create()`, and `create_button.disable()` (`home_page.py:19`) only disables the button. Pressing Enter twice during an in-flight create calls `create_session` twice and creates two sessions. The summary's stated guarantee ("a double-click yields exactly one session") is therefore not met on the keyboard path, and the test suite does not exercise it (the summary marks this as human-judgment only).
- WARNING: No error handling around the canvas lookup (`canvas_page.py:13`). `await get_services().sessions.get(session_id)` is not wrapped; a database failure or a timeout past `response_timeout=10` produces an unhandled server error with no recovery copy. Only the home page has a failure path.
- WARNING: No loading state. The canvas page does a network round trip before rendering anything, and there is no skeleton or spinner; on a slow connection the visitor sees a blank page.
- INFO: The name banner's `submit` (`identity.py:63-69`) deletes the banner and calls `on_saved`, but gives no confirmation that the name was saved beyond the header text changing. Acceptable.
- INFO: Destructive actions: none in this phase, so no confirmation dialogs are required.
- INFO: No registry (shadcn) is in use, so the registry safety audit does not apply.

---

## Files Audited

- `/Users/marco/src/marsie/gsd/quadra-gsd/app/ui/home_page.py`
- `/Users/marco/src/marsie/gsd/quadra-gsd/app/ui/canvas_page.py`
- `/Users/marco/src/marsie/gsd/quadra-gsd/app/ui/identity.py`
- `/Users/marco/src/marsie/gsd/quadra-gsd/app/ui/pages.py`
- `/Users/marco/src/marsie/gsd/quadra-gsd/.planning/phases/01-session-skeleton/01-01-SUMMARY.md` through `01-06-SUMMARY.md` (context)
- `/Users/marco/src/marsie/gsd/quadra-gsd/.planning/phases/01-session-skeleton/01-CONTEXT.md` (decisions D-01..D-04)
- `/Users/marco/src/marsie/gsd/quadra-gsd/README.md` (port 8080 confirmed)
- Not read by design: `.env` (secrets)
- Not inspected: `app/services/sessions.py` (validation copy `PROJECT_NAME_ERROR` taken from 01-03-SUMMARY.md, not re-verified in source)
