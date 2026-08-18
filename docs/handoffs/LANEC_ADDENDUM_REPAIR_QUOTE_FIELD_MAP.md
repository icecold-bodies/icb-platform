# Lane C addendum §3.0 — ICB repair-quotation document: field map + scope finding

**Date:** 17 Aug 2026 · **Author:** CA (Lane C) · **For:** BA-coordinator
**Sample read:** `231034795 Atlantic Seafoods - Ridhwan - LT 15 FB GP.pdf`
(4 pages, `C:\Users\micge\Documents\Burt Costing Model\PDF Templates`) — read page
by page, text and embedded images extracted.

---

## 1. Headline findings

1. **Exactly TWO migrations are unavoidable.** Everything else in the addendum has
   an existing home. The base Lane C brief says to STOP and surface before
   designing a migration, so this document is that stop.
2. **The letterhead is artwork, not text.** Page 1 carries a single 61 KB raster
   (`img0.png`); pages 2–4 carry a 929-byte strip (`img2.png`). The logo, the
   three branch blocks, the e-mail/web strip and the quality banner do not exist
   as text anywhere in the PDF — they are inside that image. So D1's "letterhead
   layer" is mostly **an asset to place**, not a layout to rebuild. **We need
   Michael's original artwork** (the version extracted from the sample is at
   SAP's output resolution and will look soft at print size).
3. **D2 is safe:** reportlab already renders the existing PDF cover page and can
   place an image, repeat a header/footer frame and paginate. No library switch
   is needed. (`_doc_ctx_for_record` / `build_doc_ctx` from #115 is the shell to
   extend, as D1 asks.)
4. **D3 is confirmed by the sample and is stronger than stated:** *every one* of
   the 14 lines carries a long description and a **lump-sum total only** —
   quantity and price are blank on all of them. Blank cells, never 0 or 1.
5. **D4's VAT arithmetic checks out at 15%:** 52 270,00 × 0,15 = 7 840,50, and
   52 270,00 + 7 840,50 = 60 110,50, exactly as printed.
6. **Two fields in D8 have no default source** (see §3) — the customer record has
   neither a VAT number nor an address.

---

## 2. Field map — every printed element → its source

Legend: **[E]** existing field · **[Q]** new per-quote field (rides
`result_json.input_state`, no migration) · **[S]** settings/branding ·
**[T]** admin-editable template text · **[R]** renderer-computed ·
**[M]** needs a MIGRATION.

### Page 1 — letterhead + header block

| Printed element | Source |
|---|---|
| Logo, three branch blocks, e-mail/web strip, quality banner | **[S]** branding asset (image) — original artwork needed |
| `Co. Reg. Nr: 2000/025936/07`, `VAT Nr: 451 019 0848`, customs line | **[S]** branding constants, seeded verbatim |
| `Document Date` (22-01-2026) | **[E]** `CalculationRecord.created_at` |
| `Page 1/4` | **[R]** |
| `Document Number` `R-231035462` | **[M-2]** new R-series counter |
| `Vat Num - Partner` `477 026 7526` | **[M-1]** `customers.vat_number` — does not exist |
| Customer name (large) `Atlantic Seafoods` | **[E]** `Customer.name` |
| `Tel No.` `076 037 5100` | **[E]** `Customer.telephone` / contact snapshot |
| `Email` `ridhwan.mussa@gmail.com` | **[E]** `contact_email` snapshot (migration 0035) |
| `Your Reference: Veh reg nr: LT 15 FB GP` | **[Q]** vehicle registration |
| `Your Contact` `Suzette Cocklin` + `+27 82 563 4864` | **[Q]** ICB contact + phone — **see §3.2**, `User` has no phone column |
| `Delivery Address` (3 lines) | **[Q]** — **see §3.3**, `Customer` has no address column |
| `Job note` (prints as the unresolved SAP placeholder `U_P U_ENP_JobNote`) | **[E]** WORK DESCRIPTION — already shipped in PR #142 |

### Lines table

| Printed element | Source |
|---|---|
| Columns `Description · Quantity · Price · Total` | **[E]** repair lines (PR #142) |
| Long wrapping description, **blank** qty + price, lump-sum total | **[Q]** new "total-only" line kind — extends `services/free_hand.py`, no migration |

### Totals block (page 2 in the sample)

| Printed element | Source |
|---|---|
| `Total before Discount: ZAR 52,270.00` | **[E]** selling price |
| `Discount Subtotal: ZAR 0.00 0.00%` | **[E]** `discount_amount` / `discount_input` |
| `Total Before Tax` | **[E]** `net_total` |
| `Total Tax Amount` | **[S]** VAT rate × net — rate as a `GlobalVariable`, seeded 15 % |
| `Total Amount (Including V.A.T)` | **[R]** |
| `Payment Term COD` | **[Q]** payment terms, default "COD" |
| `ZAR` prefix | **[R]** |

### Footer (every page)

| Printed element | Source |
|---|---|
| `FORWARD REMITTANCE TO:` Martie Snyman + e-mail | **[S]** branding |
| `BANKING DETAILS:` Capitec Business, Current, Acc 105 068 2114, Branch 450 105, SWIFT CABLZAJJ | **[S]** branding |
| `Printed by SAP Business One` | **drop** |
| `Carry Over: 52,270.00` at the foot of a continuing page **and** at the top of the next | **[R]** |

### Continuation header (pages 2+)

Small logo · `Original` · `Repair Quotation` · Document Number · Document Date ·
`Page n/m` → **[S]** + **[R]**.

### Terms (page 3) — all **[T]**, `PDFTemplate` rows

`NOTE A/B/C` · `V.A.T.` clause + the four cross-border points · `VALIDITY` (30
days) · `COMPLETION` · `WARRANTY` (6 months) · `TERMS OF SALES` (C.O.D.) ·
`CONDITIONS OF SALES` + Signature / Date rules.

### Page 4 — Quote Acceptance form — **[T]**

Fax `(086) 571-6181` · "I hereby accept the Icecold Bodies Quote Ref: …" ·
Signature / PRINT NAME / Date.
⚠ The sample prints `Quote Ref: 231,035,462` — thousands-separated. That is a SAP
formatting bug on a document number; **we should print `R-231035462`**, not
reproduce it. (The addendum's D7 list does not mention this page — flagging that
it exists and needs a home.)

---

## 3. The four things that need a decision before building

### 3.1 D7 has a host — no migration
`PDFTemplate` (`pdf_templates`: name, `template_data` JSON, is_active) already
exists, with an admin at `backend/app/routers/pdf_templates.py`. The terms blocks
and the acceptance form fit as template rows. **Confirmed as asked.**
The VAT RATE fits `GlobalVariable` (name/value/description). Branding constants
fit either a `PDFTemplate` row or the same settings table. None need a migration.

### 3.2 **[M-1]** Customer VAT number — MIGRATION
`Customer` has: `id, branch_id, bp_code, name, email, telephone, is_active,
is_dealer, created_at`. **No VAT number.** D8 says to add it to the customer
record rather than typing it per quote — agreed, and that is a small additive
migration (`customers.vat_number`).

### 3.3 Delivery address has NO default source
D8 says "default from the customer record where one exists". **It does not
exist** — `Customer` has no address field at all. Two options:
  * (a) capture per quote only (no migration), or
  * (b) add `customers.delivery_address` too (a THIRD migration) so it defaults.
**Needs Michael's call.** Same question, smaller, for the ICB contact's phone:
`User` has `username` and `email` but **no phone column**, so "default to the
logged-in user's name/phone" can only default the NAME unless a column is added.

### 3.4 **[M-2]** R-series document numbers — MIGRATION
`QuoteCounter` is an explicit **singleton** — `get_or_create_counter()` hardcodes
`filter_by(id=1)` and the docstring says "id=1 always". There is no series key.
So a second, independent series needs either a `series` column + a second row, or
its own table. Either way: a migration. The rest of the machinery
(`render_template`, `assign_quote_number`, immutability, the admin format
template) generalises cleanly and should be reused, exactly as D6 asks.

---

## 4. Scope: recommend a SPLIT (the addendum invites this)

The addendum says: *"If the shell work makes Lane C too large to land cleanly,
say so and propose a split (repairs UI first, document second)."*

**Recommendation: split.** Land PR #142 (the repairs + free-hand surface) as it
stands, and take the ICB letterhead document as its own follow-up lane.

Reasons, in order of weight:

1. **The document work hits the base brief's STOP condition.** Two migrations are
   unavoidable and a third is an open question (§3.3). The base Lane C brief says
   to surface before designing a migration — so it cannot be silently absorbed.
2. **Dependency order.** The document renders a repair; the repair has to exist
   first. Repairs-UI-first is the natural order, and it is independently testable
   and independently useful — Nadie can stop quoting extras and repairs outside
   the system the day #142 merges, while the letterhead is still being built.
3. **Rebase cost.** Lane C is the largest of three parallel lanes and rebases
   last. It has already absorbed one mid-flight base move (#140) and one
   cross-lane cache-buster collision. Doubling its size while A and B are still
   landing multiplies that, for no delivery benefit.
4. **The shell is reusable by design (D1), so it does not need to ride with its
   first user.** Building it as its own lane is what makes it a shell rather than
   a repair one-off.
5. **Blocked inputs.** The original letterhead artwork is not in the repo, and
   §3.3 needs a decision. Neither blocks #142.

**Proposed follow-up lane (Lane D — "ICB quotation document shell"):**
migrations (customer VAT, R-series, delivery address if ratified) → branding +
VAT settings → terms templates in the existing PDF-template admin → shell
renderer (letterhead, continuation header, carry-over, banking footer, n/m) →
repair body (total-only lines, VAT totals block) → tests per the addendum's §3.4
list → side-by-side comparison against the Atlantic Seafoods sample.

Nothing in #142 forecloses any of it: the repair costing already carries its
lines, type, work description, customer and contact, and the document builder it
would extend (`services/document_context.py`) is the one #115 established.

---

## 5. Premise banked

Cost Calculator 2 was originally intended as the repair platform. It is **not**
used that way — repairs are free-hand, which is why this work exists. Nothing
repair-specific is being built into Calculator 2. (Note for the record:
Calculator 2 does carry a bare `repair-quote-tick` that sets `is_repair` on an
otherwise normal body costing; PR #142 leaves that path exactly as it was.)
