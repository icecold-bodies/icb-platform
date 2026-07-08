# ADR 0034 — Customer-contacts in costings: write-time snapshot on the quote

**Status:** Accepted (Michael ratified Option A "full push" 8 Jul 2026; the pattern itself —
denormalized snapshot + SET NULL FK — was pre-ratified in the WO defaults)
**Date:** 2026-07-08
**Numbering note:** cut as 0034 on the `backport/v1.39-base` deploy line, following ADR 0033's
convention — `main`'s ADR chain holds 0029–0032, so the next shared-safe number is used to avoid a
same-number/different-content collision when the lines reconcile.

## Context

`customer_contacts` (WO v4.34.1 §0.6 — "Nadie's reality") gave every customer N contact people
with one DB-enforced primary, plus full CRUD in the SPA Customers admin. But the **quote flow
never asked which person the quote is for**: `calculations` carried only `customer_id`, the quote
PDF's existing `ATTENTION:` row rendered the *customer company name* (redundant with the MESSRS
line above it), and the pre-job check emails named no person at all. Nadie picks the person in her
head and re-types it in Outlook.

Two sub-decisions needed settling:

1. **Live join or snapshot?** If the costing only stores `contact_id`, a later rename/re-email of
   the contact silently rewrites what every historical quote *appears* to have said — the same
   trap ADR 0016 (deprecate-not-drop) and the `chassis_records.edited_by_name` write-time snapshot
   already solved elsewhere.
2. **What happens when a contact is deleted?** Contacts soft-delete (`is_active=false`) in normal
   operation, but a hard `DELETE` must not cascade away a quote, and must not leave a dangling FK.

## Decision

**Denormalized write-time snapshot on the costing row** (migration 0035, all columns nullable):

- `calculations.contact_id` — FK → `customer_contacts.id`, **`ondelete=SET NULL`**: traceability
  while the row lives; a hard delete nulls the pointer and cascades nothing.
- `calculations.contact_name / contact_email / contact_telephone / contact_role` — copied from the
  contact **at save time** by the `_contact_snapshot` chokepoint in the `/api/approve` handler
  (both the create and the edit-overwrite paths). These are what every downstream consumer renders
  — the quote is historically accurate forever, regardless of later contact edits or deletes.
- The chokepoint **422s loudly** on a contact that doesn't belong to the selected customer or is
  inactive — that pairing can only be produced by a stale or hand-crafted payload.

Downstream consumers read the snapshot, never join the live row:

- **PDF** (`report_engine.build_explosive_quote_context`): `ATTENTION:` becomes the contact name;
  `TEL NO`/`EMAIL` prefer the contact's with per-field fallback to the customer's. No contact →
  every field renders exactly as before (byte-identical legacy PDFs).
- **Check emails** (all variants — per-signer sales/planner, CC/observer, legacy mailto): a
  `For attention of: {contact_name}` line when present, absent otherwise.
- **Serializers**: list carries `contact_name`; detail carries all five fields (drives edit-mode
  re-selection in the calculator and the SPA CostingDetail "Attention" row).

**UX (both maintained calculators — calculator.js v136 + calculator2.js v123 parity):** an
"Attention" picker under the Customer selector. Contacts load per customer; the **primary contact
auto-selects** (sole contact auto-selects even when not primary); zero contacts → an empty state
with an inline "+ Add now" mini-form. The selection rides the LAST_SESSION snapshot, the v1.39.9
return-state round-trip, and the `?edit=` re-hydration path (`setCustomer(customerId, contactId)`).

**Auth enabling change:** `POST /api/customers/{id}/contacts` relaxed `require_admin` →
`require_user` so the quick-add works for sales users mid-quote. Create is additive and audited
(`created_by`/`updated_by`); **update / set-primary / delete stay admin-only**. A quick-added
first contact is marked primary by the client (`is_primary: !allContacts.length`).

## Consequences

- Historical quotes are immune to contact-table churn; the FK gives live traceability until a hard
  delete, and even then display values survive (`SET NULL` + snapshot proven by test).
- Snapshot staleness is a *feature* here (the quote shows what was sent), but a re-save of an
  edited costing re-snapshots — editing refreshes the contact details deliberately.
- Old rows and no-contact saves have all-NULL contact fields → every consumer falls back to
  pre-WO output exactly (PDFs byte-identical, email bodies unchanged).
- Repair quotes inherit the costing's contact — `RepairPhasePanel` has no customer selection of
  its own, so no separate handling (discovery §3.0f).
- The two "Customers" admin surfaces are **different screens, not a duplicate route** (legacy
  Jinja `admin_customers.html` under User Setup manages customer rows only; the SPA
  `/mes-app/admin/customers` owns contacts). Left as-is; flagged to the BA rather than removed —
  the legacy page belongs to the whole legacy admin suite's lifecycle, not this WO.
