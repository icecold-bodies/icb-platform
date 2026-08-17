# ADR 0039 — The END USER on a costing: a per-customer book + a write-time snapshot

**Status:** Accepted (WO v1.47 lane B; the pattern itself — per-customer list + denormalized
snapshot + SET NULL FK — was pre-ratified in the WO defaults, which mirror ADR 0034)
**Date:** 2026-08-17
**Numbering note:** cut as 0039 on the `backport/v1.39-base` deploy line (highest ADR here is
0038). Unrelated to migration 0040, which carries this change — the two chains number
independently.

## Context

Nadie, 17 Aug 2026: **ICB's customer is often a reseller or a middleman — the body is actually
FOR someone else.** The MES captured only `customers` + `customer_contacts` (ADR 0034), so the
end user never reached a quote document. Nadie kept that fact in her head and re-typed it in
Outlook, which means the company the body is genuinely for is absent from every artefact the
business keeps.

The shape she asked for was explicit: "a table that contains the end user and the contact
person" — i.e. one row is the end-user COMPANY *plus* its person, not two related tables.

Three sub-decisions needed settling, and ADR 0034 had already answered all three one level in:

1. **Live join or snapshot?** Storing only `end_user_id` means a later rename silently rewrites
   what every historical quote appears to have said.
2. **What on delete?** A hard delete must neither cascade away a quote nor dangle.
3. **Where is it managed, and is it ever mandatory?**

## Decision

**A per-customer end-user book plus a denormalized write-time snapshot on the costing**
(migration 0040), deliberately the twin of the contact pattern rather than a new idea:

- `icb_costings.customer_end_users` — `customer_id` FK **CASCADE** (an end-user row is
  meaningless without its customer), `company_name` **NOT NULL** and every other field
  optional, soft-delete via `active`, and the partial unique index
  `uq_customer_end_users_one_primary` mirroring `uq_customer_contacts_one_primary`.
- `calculations.end_user_id` — FK → `customer_end_users.id`, **`ondelete=SET NULL`**.
- `calculations.end_user_company / _contact_name / _contact_email / _contact_telephone /
  _contact_role` — copied at save time by `_end_user_snapshot()`, a **sibling of**
  `_contact_snapshot()` in the `/api/approve` handler: same chokepoint, same transaction, both
  create and edit-overwrite paths. It **422s loudly** on an end user that doesn't belong to the
  selected customer or is inactive — a pairing only a stale or hand-crafted payload produces.

The contact snapshot's own behaviour is untouched; the two resolvers write disjoint column sets
and a unit test pins that they cannot bleed into each other.

**Documents.** The two lines are built in ONE place — `document_context.build_end_user_lines()`,
returning `ctx["end_user_lines"]` — so Excel, Word and PDF inherit identical wording by
construction and cannot drift. Rendered directly under the client line as `End user: {company}`
and, when present, `End user contact: {name}`. **No end user → an empty list → the renderers
emit nothing**: not a blank line, not an empty label. The xlsx renderer's header rows became a
counter rather than hardcoded 3/4/5/6 so the block can be absent; a test pins that with no end
user the client line, section header and dimension row land on exactly the rows they used to.

**UX.** An "End user (optional)" picker directly below the Attention picker in both maintained
calculators (`calculator.js` + `calculator2.js` — ADR 0034 made that parity an invariant), with
the same inline "+" quick-add and the same `require_user` relaxation on CREATE so a sales user
can add one mid-quote. The selection rides the LAST_SESSION snapshot and the `?edit=`/duplicate
re-hydration path via `setCustomer(customerId, contactId, endUserId)`.

**One deliberate divergence from the contact picker: nothing auto-selects.** The Attention
picker defaults to the primary contact, which is a safe guess about who to address. An end user
is a *commercial claim about who the body is for*; defaulting to the primary would put a company
name on a quote nobody chose. Only an explicit preset (edit / duplicate / session restore)
re-selects.

**Management** lives on the existing Customers admin screen as a second section beside Contacts
— no new admin page.

## Consequences

- Historical quotes are immune to end-user-book churn; the FK gives live traceability until a
  hard delete, and even then the display values survive (proven by test, both at unit level and
  through the real `/results/{id}/export/*` route).
- Nothing became mandatory. A costing with no end user is byte-for-byte the pre-WO costing at
  every layer: NULL columns, absent document lines, absent detail row.
- Re-saving an edited costing **re-snapshots** — editing deliberately refreshes the values, same
  as the contact snapshot.
- The end user is **not** wired into pre-job cards, emails, or the ERP/VCL integrations. Those
  were out of scope and remain untouched; the snapshot columns are there when they are wanted.
- `calculator2.js` keeps parity even though Calculator 2 is slated for elimination in the costing
  redesign — a live page with a missing picker would silently drop the end user from quotes saved
  there, which is worse than the small duplication.
