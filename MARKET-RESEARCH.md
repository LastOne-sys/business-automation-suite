# Demand review · 28 September 2026

This is a small qualitative sample of real briefs, not a market-size study. An advertised need proves that a buyer described a problem; it does not prove they will buy our implementation. The products below are independent implementations of recurring requirements, not copies of customers' systems.

## 1. QuoteDesk — quote preparation from customer requests

**Evidence:** [RFQ-to-quote prototype, n8n Community](https://community.n8n.io/t/seeking-estimates-n8n-developer-for-a-small-rfq-to-quote-prototype/312281), original post 10 September 2026. Request: extract requested items, match an approved catalogue, flag uncertain matches and prepare a quotation. The buyer is still at scoping/quotation stage in the original post; this is not proof of a awarded contract.

**Target:** parts distributors, small wholesalers, installers with a controlled price list.

**This delivery:** controlled CSV catalogue, explicit SKU/quantity input, Decimal arithmetic, discounts, unknown-code review, approval, browser print-to-PDF and approved CSV export. Product/pricing snapshots preserve old offers.

**Gap to that specific brief:** arbitrary text-PDF item extraction and Excel XLSX output are not implemented; CSV opens in spreadsheet programs. Start a paid pilot with one agreed input format and client catalogue.

## 2. InvoiceDesk — invoice review and approved export

**Evidence:** [Invoice Ingestion Pipeline + Validation Dashboard](https://www.upwork.com/freelance-jobs/apply/Invoice-Ingestion-Pipeline-Validation-Dashboard-prem_~022092287777428636654/), posted 25 August 2026. The customer explicitly separates an extraction service and ERP integration from the required pipeline and review dashboard. [Automate Invoice Processing Pipeline](https://www.upwork.com/freelance-jobs/apply/Automate-Invoice-Processing-Pipeline_~022097786808889948478/), posted 9 September 2026, advertises $1,500 for a broader extraction/integration scope.

**Target:** small purchasing and bookkeeping teams checking incoming supplier invoices.

**This delivery:** text PDF intake, labelled field extraction, original text side-by-side, duplicate checks, date/amount validation, human approval and approved CSV. No automatic financial action.

**Gap:** no vendor-independent OCR, mailbox ingestion or accounting connector. A client pilot must identify invoice formats and its import schema before pricing integration work. Advertised broader budgets are not our promised sale price.

## 3. SupportDesk — knowledge-backed replies and operator handoff

**Evidence:** [AI support-system brief](https://community.n8n.io/t/buscamos-ai-automation-engineer-para-construir-nuestro-sistema-de-soporte-con-ia/315655), 22 September 2026: classify enquiries, answer FAQs, consult systems and escalate complex issues. That financial-services brief requires substantially more than this local product.

**Target:** a small service business with a short, approved FAQ and an operator reviewing enquiries.

**This delivery:** editable knowledge articles, public enquiry form, conservative keyword search with verbatim answer/source, ambiguity handoff, operator reply, draft email download, local ticket history.

**Gap:** no generative AI/RAG, order API, WhatsApp or automatic outgoing mail. The demo labels search honestly. Do not describe it as a deployed payment-support agent.

## 4. BookDesk — appointment intake and reminders

**Evidence:** [Home Service Lead Conversion / CRM & Automation](https://www.upwork.com/freelance-jobs/apply/Home-Service-Lead-Conversion-Revenue-Operations-CRM-Automation-Specialist_~022102562276524042972/), checked 28 September: booking, confirmations, reminders and no-show follow-up are specified as part of a broader business process. [GHL specialist brief](https://www.upwork.com/freelance-jobs/apply/GHL-specialist-needed_~022096037178252522869/) likewise requests structured pre-call summaries and follow-up/reminder rules.

**Target:** a consultant or local service provider with one appointment calendar.

**This delivery:** real availability calculation, explicit timezone, serialized conflict checking, reservation/cancellation, ICS export, idempotent 24-hour reminder drafts.

**Gap:** no GHL/SMS/Google Calendar integration; no-show recovery and automatic reminders are not delivered. Public internet access requires deployment, not merely sending a localhost link.

## Delivery priority and commercial packaging

1. QuoteDesk: a bounded pilot with an agreed catalogue and request format.
2. InvoiceDesk: pilot on representative invoices with measured field correction rate.
3. BookDesk: confirm actual schedule and integration needs before promising online operation.
4. SupportDesk: collect approved FAQ and evaluate questions before offering AI expansion.

For every pilot: specify inputs, outputs, exceptions, installation location, acceptance examples, handover and support period. Track time saved and errors only after measuring the customer's baseline. No fabricated testimonials, customer logos, production references or estimated conversion uplift are included.
