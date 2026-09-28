# Verification · 28 September 2026

Environment: Windows, bundled Python 3.12.14 runtime, pypdf 6.10.0, tzdata 2026.3, Chromium through Playwright. The four apps are bound to loopback only.

## Automated checks performed

- **34 unit / HTTP tests passed** (`python -m unittest discover -s tests -q`). Covers Decimal calculations, invalid quantities, catalogue atomicity and currency integrity, quote snapshots, unknown-code approval blocking, invoice duplicates/arithmetic/precision/correction/reapproval, immutable paid records, backup record recovery, persistence, knowledge sources and ambiguity escalation, operator workflow, configurable booking resources, consent, simultaneous reservation conflicts, overlapping durations, cancellation releasing slots, unique reminders and cancellation, ICS/CSV injection escaping, password/session revocation, origin/Host validation, unauthorized data access and login throttling.
- **Four Chromium end-to-end flows passed** at 1440×1000 and layout overflow checks at 390×844. Quote create → verify €112.30 → approve → print action; invoice correct → approve → CSV; public support question → source → operator draft → `.eml`; public booking → ICS → cancellation. No JavaScript page errors recorded.
- **Real text PDF test passed**: generated `examples/sample-invoice.pdf`, extracted its text with pypdf, parsed fields, validated totals. Non-PDF input rejected. No OCR accuracy claim.
- Desktop/mobile screenshots saved under `screenshots/`; representative desktop, public and mobile views visually inspected.

## Issues found and fixed during verification

- SQLite connection lifetime on Windows: context-managed connections now explicitly close; backup regression test passes.
- Isolated session-cookie names for the four products so logging into one does not replace another's cookie.
- Money with more than two decimal places is rejected rather than silently rounded during invoice validation.
- Catalogue currency cannot be silently relabelled after importing prices.
- Demo launcher checks for an existing listener and server address reuse is disabled.

## Not verified / not delivered

No fresh-machine internet dependency installation, public hosting, HTTPS proxy, penetration test, external email/SMS/WhatsApp/CRM integration, generative AI, OCR, paid-client deployment or commercial performance measurement. Browser tests use explicit synthetic demo workspaces. Privacy/retention requirements for a particular customer need agreement before real-data deployment.

The screenshots and examples are demonstrations, not customer case studies. Review the README boundaries before offering a client installation.

## Distribution check

All four ZIPs were extracted into separate temporary folders and started independently with an empty workspace. Each selected the correct product, served its interface and generated a unique local password. No databases or password files were included in the archives. See archive-results.json.
