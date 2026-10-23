---
phase: 03
review: 03-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "A failed save discards the participant's draft"
  - id: WR-02
    severity: warning
    disposition: open
    title: "A late Realtime echo can resurrect a card the participant just deleted"
  - id: WR-03
    severity: warning
    disposition: open
    title: "Move up/down becomes a silent no-op once float precision is exhausted"
  - id: WR-04
    severity: warning
    disposition: open
    title: "`reorder_card` writes an order computed for one quadrant without checking the card is still in it"
  - id: WR-05
    severity: warning
    disposition: open
    title: "`_write` can notify and render into a client that has already gone"
  - id: IN-01
    severity: info
    disposition: open
    title: "Unused fields on `_CardWidgets`"
  - id: IN-02
    severity: info
    disposition: open
    title: "`deleted_at` is stamped with the app server's clock, everything else by the database"
  - id: IN-03
    severity: info
    disposition: open
    title: "Test helpers copy-pasted across five UI test files and three integration files"
  - id: IN-04
    severity: info
    disposition: open
    title: "Fixed `asyncio.sleep(0.1)` settles make several UI assertions timing-dependent"
open: 9
total: 9
recorded: 2026-10-23T17:17:21.263Z
---

# Phase 03: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
