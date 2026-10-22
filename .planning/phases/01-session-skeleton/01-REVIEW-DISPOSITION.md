---
phase: 01
review: 01-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "Home page can create duplicate sessions (Enter re-entry, re-enabled button) (external: ui-audit)"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Realtime key-log protection is ineffective and an invalid URL leaks the key at ERROR level (external: security-audit R1/R2)"
  - id: WR-03
    severity: warning
    disposition: open
    title: "A too-short `STORAGE_SECRET` is echoed verbatim in the startup traceback"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Startup check phases have no hard timeout (external: security-audit R5)"
  - id: WR-05
    severity: warning
    disposition: open
    title: "Canvas page has no handling for database failures (external: ui-audit)"
  - id: WR-06
    severity: warning
    disposition: open
    title: "Banner and dialog handlers are not idempotent and can raise on a deleted element"
  - id: WR-07
    severity: warning
    disposition: open
    title: "`cards.author` and `workspaces.closed_by` CHECKs accept whitespace-only values (external: security-audit R4)"
  - id: WR-08
    severity: warning
    disposition: open
    title: "`integration_settings` turns any configuration error into a skip, so the integration suite can pass vacuously"
  - id: IN-01
    severity: info
    disposition: open
    title: "`/healthz` returns raw exception text without authentication"
  - id: IN-02
    severity: info
    disposition: open
    title: "`SESSION_ID_RE` uses `$`, so `.match()` accepts a trailing newline"
  - id: IN-03
    severity: info
    disposition: open
    title: "In `warn` mode a failed check leaves the Realtime client running and the state can never recover"
  - id: IN-04
    severity: info
    disposition: open
    title: "Quadrants are sorted twice"
  - id: IN-05
    severity: info
    disposition: open
    title: "A real hosted-project ref is committed in `.env.example` and the README"
  - id: IN-06
    severity: info
    disposition: open
    title: "The e2e home-create test can leave rows behind in the hosted database"
open: 14
total: 14
recorded: 2026-10-22T22:30:27.771Z
---

# Phase 01: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| WR-07 | warning | open | - |
| WR-08 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
