# QuoteDesk

Из заявки — в точное предложение

This archive contains one independently installable application. The shared reference below describes the complete product family.

# Four business applications · v1.0

Four independent, single-business local applications built for installation and scoped client pilots. They have real SQLite persistence, authenticated operator workspaces, browser interfaces, exports and business-rule tests. They are **not four completed cloud SaaS services**, and no client results or paid deployments are claimed.

| Product | Business outcome | Port |
|---|---|---|
| QuoteDesk | Customer request → catalogue prices → review → printable quotation | 8111 |
| InvoiceDesk | Text/PDF invoice → editable fields → validation → approval → CSV | 8112 |
| SupportDesk | Customer question → published knowledge source or operator queue → reviewed reply | 8113 |
| BookDesk | Available slot → conflict-safe reservation → cancellation/calendar/reminder drafts | 8114 |

## Windows installation

1. Install Python 3.11+ with **Add Python to PATH**.
2. Open PowerShell in this folder. Run `powershell -ExecutionPolicy Bypass -File install.ps1`. This creates a local virtual environment and installs `pypdf` and IANA timezone data. Internet is needed for this one-time dependency installation.
3. In this extracted folder double-click **START.cmd** for an empty workspace or **DEMO.cmd** for separate synthetic demo data. Leave the terminal running.
4. Open the printed local address. The initial administrator password is in `data/<project>/FIRST-LOGIN.txt` (or `<project>-demo` for demo mode).
5. Change the password in Settings. The initial password file is removed after a successful change. No shared default password exists.

On macOS/Linux: create a Python virtual environment, install `requirements.txt`, then run `python run.py --project quote` (or `invoice`, `support`, `booking`). Add `--demo` for demo data. `--port` and `--data-dir` are optional.

Each ZIP under `dist/` is independently installable; it includes its own `core/`, `web/`, launcher, requirements and product README. Do not copy live `data/` into a public repository or portfolio.

## Daily use

- **QuoteDesk**: import `sku,name,price` CSV in Catalogue → add client and `sku,quantity` rows → check unknown codes → approve → Print/PDF. Exports include approved quotes only. Prices are snapshots; changing a catalogue never changes old quotations. Unknown codes require a new corrected quote; archive the old one.
- **InvoiceDesk**: paste labelled text or extract a text PDF → review original and fields → correct totals/dates → approve → mark paid. CSV includes approved/paid invoices only. Uploads do not initiate payments or write to accounting software.
- **SupportDesk**: write approved articles with keywords → use `/public` to submit a question → view the source or escalation → operator reviews a reply → download `.eml` and send from an email client. Closing a ticket does not send email.
- **BookDesk**: configure business name, timezone and hours → use `/public` for bookings → download ICS or save cancellation link → admin can cancel and prepare unique reminder drafts for the next 24 hours. The default services are 30-minute consultation and 60-minute extended meeting with one specialist.

## Data and backups

Each product has a separate SQLite database. Demo data lives separately and is seeded only into an empty demo workspace.

```text
python run.py --project quote --backup quotation-backup-2026-09-28.sqlite3
```

Use a new backup filename. Add `--demo` to back up the demo database. A live-consistent SQLite backup includes records, configuration, password hash, sessions and audit history, so protect it as confidential. To restore, stop that application, retain the current database as a rollback copy, then copy the backup to its `data/<project>/database.sqlite3`. On restart, change the admin password to revoke restored sessions. Never restore over a running database.

## Verification

```text
python -m unittest discover -s tests -v
```

See `VERIFICATION.md` for the checks actually run, `MARKET-RESEARCH.md` for demand evidence, and `HANDOVER-RU.md` for the Russian guide.

## Boundaries of this release

- Binds **only to 127.0.0.1**. Public pages work on the same computer. Internet booking/support requires deployment work, HTTPS, production serving, configured origin/host policy, operational monitoring and a real privacy notice. Do not expose this development HTTP server directly to the internet.
- Single administrator; no staff roles, tenant isolation, account recovery or encrypted-at-rest database.
- No LLM calls: support is conservative keyword retrieval with verbatim sources; invoice extraction is label-based. These are deliberately labelled as such in the UI. No AI provider account or payment is required.
- PDF: text layer only, up to 2 MB / 10 pages. No OCR, no guaranteed extraction of arbitrary invoice layouts or line items; human verification is required. PDF originals are processed in memory; extracted source text is retained.
- Quote input: structured SKU/quantity text or CSV pasted into the form, not general natural-language RFQ interpretation. Amounts are catalogue totals before any separately agreed taxes/delivery. All prices within one quote use one currency.
- Invoice validation checks fields, dates and arithmetic, not tax-law compliance or document authenticity. No bank/ERP/QuickBooks integration.
- Email files and booking reminders are **drafts**, never silently sent. No SMTP, Gmail, WhatsApp, SMS, Google Calendar or payment integration. ICS download is not calendar synchronization.
- Bookings: configurable specialists and 30/60/90/120-minute services, weekdays, 30-minute grid, 60-day horizon, minimum 30-minute notice. Multi-location schedules and rescheduling are not included; cancel and create a new booking instead.
- Historical records are retained locally. A deployment involving real personal data needs an agreed retention/deletion process.

Sell this version as an installation plus a precisely scoped pilot with these boundaries, not as an unqualified enterprise solution.

## This product

Run `python run.py` or `python run.py --demo`. URL: http://127.0.0.1:8111. Data: `data/quote` (demo: `data/quote-demo`).
