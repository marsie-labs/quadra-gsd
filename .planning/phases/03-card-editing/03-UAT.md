---
status: testing
phase: 03-card-editing
source: [03-VERIFICATION.md]
started: 2026-10-23T17:22:46Z
updated: 2026-10-23T17:22:46Z
---

## Current Test

number: 1
name: Two-window inline edit
expected: |
  A shows the new text with '(edited)' at once; B shows the same within about 1 s without reload and still shows it after reload.
awaiting: user response

## Tests

### 1. Two-window inline edit
Two real browser windows on one session (uv run python -m app): click a card's text in window A, change it, press Enter. Reload window B.
expected: A shows the new text with '(edited)' at once; B shows the same within about 1 s without reload and still shows it after reload.
result: [pending]

### 2. Real-browser editor behaviour
Open a card's menu (also with touch emulation) and choose Edit; type two lines with Shift+Enter, press Enter; Edit again and click elsewhere; Edit again and press Esc; clear the text and click away.
expected: Editor takes focus with no refocus fight (menu has no-refocus); both lines show after Enter; blur saves; Esc restores the old text; empty text shows the error and saves nothing.
result: [pending]

### 3. Cross-window draft protection (D-04)
Two real windows: in B start editing a card without saving; in A edit the same card and press Enter; press Enter in B. Repeat but delete the card from A.
expected: B's editor and draft stay intact; after B's Enter both windows show B's text; on delete B's editor closes and shows 'This card was deleted.'
result: [pending]

### 4. Move to submenu and delete
Open a card's menu, hover or tap 'Move to', pick DOES; pick Delete on another card (two windows).
expected: The Move to submenu opens beside the menu on hover and on tap; the card jumps to the bottom of DOES at once here and within about a second in the other window; Delete removes the card at once with 'Card deleted' in both.
result: [pending]

### 5. Move up / Move down across windows
Add three cards to IS; use Move up and Move down in window A; look at window B and reload.
expected: B shows the same order within about a second and after reload; the first card's Move up and the last card's Move down are greyed out (a single card has both greyed).
result: [pending]

### 6. Backstop: simultaneous writers on one card
Two writers update the same card at the same moment (two windows saving an edit/reorder of one card simultaneously, or two scripted PostgREST updates fired in parallel against the hosted project, repeated).
expected: The row's final updated_at is the newest of the two stamps and every client ends on that row.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
