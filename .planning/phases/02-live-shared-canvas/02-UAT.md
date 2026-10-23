---
status: testing
phase: 02-live-shared-canvas
source: [02-VERIFICATION.md]
started: 2026-10-23T11:51:25.103Z
updated: 2026-10-23T11:51:25.103Z
---

## Current Test

number: 1
name: Two real browsers, live card (SC2). Run `uv run python -m app`, open one session link in two real browsers (one private window), name browser A, add a card in IS.
expected: |
  Browser B shows the card within about a second, in IS, as 'author · HH:MM' with the full timestamp on hover.
awaiting: user response

## Tests

### 1. Two real browsers, live card (SC2). Run `uv run python -m app`, open one session link in two real browsers (one private window), name browser A, add a card in IS.
expected: Browser B shows the card within about a second, in IS, as 'author · HH:MM' with the full timestamp on hover.
result: [pending]

### 2. SQL-editor demo (SC3). With the session open in both browsers, run the insert from README 'Live updates' in the Supabase Dashboard SQL editor, then the text update, then `deleted_at = now()`.
expected: The row appears in IS in both browsers with no reload, the edit shows, then the card disappears.
result: [pending]

### 3. Browser offline/online (SC4). In browser A, DevTools > Network > Offline for ~10 s; add a card in browser B; set A back online.
expected: A shows the card without a manual reload.
result: [pending]

### 4. Server restart (SC4). Ctrl-C the server, add a card via the SQL editor, start the server again, reload both browsers, then GET /healthz.
expected: Both browsers show every card including the one added while down; /healthz reports realtime 'verified'.
result: [pending]

### 5. Name dialog, inline error, double-click (SC1). In a fresh private window type text in IS and Add; Cancel; Add again, enter a name, Continue. Then Add on an empty field and with a 501-character paste. Then double-click Add quickly.
expected: Cancel keeps the text and writes nothing; Continue stores 'name · HH:MM' and removes the banner; 'Card text is required (max 500 characters)' appears under that field only; one card appears on double-click.
result: [pending]

### 6. Multi-tab author backstop (02-02 truth). In one browser open the session in tab A and tab B, both unnamed. In A type a card and Add so the name dialog opens; in B save the name "Zed"; back in A enter "Amy" and Continue.
expected: The stored and shown author is "Zed" (the name already in effect), not "Amy".
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
