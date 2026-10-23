# Phase 3: Card Editing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-23
**Phase:** 3-Card Editing
**Areas discussed:** Edit interaction, Card action controls

---

## Edit interaction

### Edit mode
| Option | Description | Selected |
|--------|-------------|----------|
| Inline in place | Text becomes a textarea inside the card; reuses validation/error pattern | ✓ |
| Edit dialog | ui.dialog with textarea + Save/Cancel | |
| You decide | Planner picks | |

### Save/cancel
| Option | Description | Selected |
|--------|-------------|----------|
| Enter/blur saves, Esc cancels | Shift+Enter newline; unchanged text = no write | ✓ |
| Explicit Save/Cancel buttons | Enter saves, Esc cancels, blur does nothing | |
| Enter saves, Esc/blur cancels | Clicking away discards | |

### Remote change while editing
| Option | Description | Selected |
|--------|-------------|----------|
| Keep my draft, last save wins | Textarea untouched; save overwrites (LWW); cancel shows latest | ✓ |
| Keep draft + show a hint | Plus "Someone else changed this card" note | |
| Replace my draft | Remote update discards typing | |

### Ownership
| Option | Description | Selected |
|--------|-------------|----------|
| Anyone; author stays original | No edited_by; no name gate on edit | |
| Anyone; show 'edited' marker | Plus "(edited)" display marker | ✓ |
| Anyone; record last editor | edited_by column + name gate | |

### Edited flag trigger
| Option | Description | Selected |
|--------|-------------|----------|
| Text edits only | Cheapest reliable text-change signal (e.g. text_updated_at) | ✓ |
| Any change (updated_at > created_at) | No schema work; moves also show "(edited)" | |
| You decide | Planner picks | |

**Notes:** Moves/reorders bump updated_at, so "(edited)" needs a text-specific signal.

---

## Card action controls

### Placement
| Option | Description | Selected |
|--------|-------------|----------|
| ⋮ overflow menu per card | Edit, Move to →, Move up/down, Delete; click text also edits | ✓ |
| Visible icon row | Always-shown icon buttons | |
| Hybrid | ↑/↓ visible; Move/Delete in menu | |

### Delete
| Option | Description | Selected |
|--------|-------------|----------|
| No confirm, instant | Optimistic removal + "Card deleted" toast | ✓ |
| Toast with Undo | ~5 s undo clearing deleted_at | |
| Confirm dialog | "Delete this card?" | |

### Move target
| Option | Description | Selected |
|--------|-------------|----------|
| End of target quadrant | max order_index + 1024, same as add | ✓ |
| Top of target quadrant | min order_index − 1024 | |

### Edges
| Option | Description | Selected |
|--------|-------------|----------|
| Disabled in menu | Greyed out at edges; stable menu shape | ✓ |
| Hidden | Only valid actions shown | |

---

## Claude's Discretion

- Reorder mechanics and concurrent reorder handling (not discussed)
- Optimistic feedback and rollback presentation (not discussed)
- Mid-edit delete/move by another participant
- updated_at maintenance (trigger vs service), write path (update vs RPC), re-entrancy guards

## Deferred Ideas

None.
