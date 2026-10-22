# Phase 1: Session Skeleton - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-22
**Phase:** 1-Session Skeleton
**Areas discussed:** Name prompt flow

---

## Name prompt flow

### Prompt style for first-time visitor

| Option | Description | Selected |
|--------|-------------|----------|
| Blocking dialog (Recommended) | Modal over canvas, can't dismiss without a name | |
| Inline banner | Canvas fully usable; banner at top asks for name | ✓ |
| Separate join screen | Full page before canvas renders | |

**User's choice:** Inline banner

### Unnamed participant attempts to add a card

| Option | Description | Selected |
|--------|-------------|----------|
| Ask name at that moment (Recommended) | Card action opens name prompt first; card saves after | ✓ |
| Fallback 'Anonymous' | Card saved with author 'Anonymous' | |
| Disable card actions | Controls greyed out until name set | |

**User's choice:** Ask name at that moment

### Can the name be changed later

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, from header (Recommended) | Edit control in header; applies to future cards | |
| No, fixed per browser | Set once; change only by clearing browser storage | ✓ |

**User's choice:** No, fixed per browser

### Display name rules

| Option | Description | Selected |
|--------|-------------|----------|
| Trimmed, 1–40 chars (Recommended) | Trim, reject empty, max 40, duplicates allowed | ✓ |
| Trimmed, 1–20 chars | Shorter cap | |
| You decide | Claude picks limits | |

**User's choice:** Trimmed, 1–40 chars

---

## Claude's Discretion

- Canvas layout & header
- Home & not-found pages
- Startup Realtime check behavior
- session_id token format, name storage mechanism

## Deferred Ideas

None.
