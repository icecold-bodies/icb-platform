# CA Day Report — 10 Aug 2026 (for BA-coordinator)

**Line:** `backport/v1.39-base` · **Dev :8000, prod, and tag `v1.45.2` all at `f4b1e1d` — lockstep, verified.**
Five PRs shipped, merged, prod-deployed and tagged. Every PR CI-green on its exact head SHA,
live-verified on :8000 after merge, and independently verified on prod after deploy
(commit + fresh `ActiveEnterTimestamp` + code-on-disk grep + route probes).

**One incident to read first — §Incident below. I emailed a real customer's priced costing
to an outside domain during verification.** It is contained and the product now prevents it,
but the exposure assessment is yours.

## Shipped ledger

| PR | What | Notes |
|----|------|-------|
| #115 | Excel/Word/PDF preview + export, options dialog, multi-ratio totals, Nadie's permanent-price permission, body-length display | One shared context builder → layout parity is structural, not hoped for. `costings.price_master_edit` seeded `{admin, full}` |
| #117 | PDF export keeps the whole cover on page 1 | Measured with ReportLab `wrap()`, not eyeballed: pre-block 227pt, 295pt left, tail needed ~309pt |
| #118 | Email the Preview / Export document to a recipient | First attachment-capable mail path in the app |
| #119 | Internal recipients only — deny-by-default, fail-closed | Direct response to the incident |
| #120 | Permission bootstrap serialized with a pg advisory lock | Fixes a **live prod defect** found in the 8 Aug boot log |

**Tag `v1.45.2`** on `f4b1e1d` — first tag since v1.43.2 (22 Jul), so it covers **#110–#120**.
Verified the banked way: annotated tag-object SHA identical local ↔ origin, `cat-file -t` = `tag`,
resolves to the commit confirmed running on prod. No migrations, no new dependencies all day.
Cache-busts: `calculator.js` v146→150 (collision-checked each time).

## Incident — customer costing emailed outside the company (10 Aug, 11:27)

**What happened.** My post-merge verification script for #118 drove the live send path on
:8000. **The dev box has SMTP configured** (smtp2go). I had assumed it did not — and wrote that
assumption into the script as a comment instead of checking it. Two real emails went out:

| To | Attached | Outcome |
|----|----------|---------|
| `x@y.co.za` | `Costing_CHILLER_MEDIUM_1672_admin.pdf`, 19,892 B, full line items | **`y.co.za` has live MX records** — reached a third party's mail infrastructure |
| `buyer@customer.co.za` | same document, totals-only, 3,545 B | No MX/A record — failed at DNS |

Both Cc'd `micger123@gmail.com`, so copies are in your inbox. Content: **A32810/08/2026 —
360 DEGREES CARRIERS (PTY) LTD**, with materials R82,823.98 and totals to R248,471.94.

**Root cause:** treating "this is a test box" as a fact rather than a checkable condition.
The feature itself was correct; nothing in the product stopped a costing reaching any address.

**Contained by:** #119 (internal-only, server-side, fail-closed); the offending script disabled
in place with the reason in its docstring; and a standing rule banked — *never drive a send path
against a running server without first asserting the box cannot send; stub the transport and
assert on the message instead, which needs no server at all.*

**Still yours:** whether the `y.co.za` delivery needs any action. smtp2go's log holds the remote
server's response — that's the fastest way to know if a mailbox accepted it or it bounced.

## Prod defect found and fixed (#120)

The 8 Aug deploy log carried `PERMISSION BOOTSTRAP FAILED: UniqueViolation` on `export.word`.
Prod runs `uvicorn --workers 4` and **every worker seeds permissions at startup**, so any deploy
adding a new key races. The duplicate row is harmless — **the loser's whole transaction rolled
back, taking the role grants with it**, and grants are what gate users. It was silent: the worker
still logged "Application startup complete". A bad roll could have left Nadie locked out of the
very feature that deploy shipped.

Fixed with a transaction-scoped advisory lock. **Prod boot after deploying it: 4 workers,
zero `BOOTSTRAP FAILED`, four clean startups** — which also closes the open question about
whether those grants survived. No manual restart or DB query needed.

## Premise corrections the BA should bank

1. **python-docx was already a declared dependency** (WO v4.33). The #115 WO said Word export
   would need a new one and warned about lazy-import silent-skip. Word export was new; the
   dependency was not.
2. **`PUT /api/bom/{id}` wrote no audit rows at all** before this work. The WO said to "verify
   `BomOverrideHistory` rides along" — there was nothing to verify. The audit trail is an
   **addition**, and it now fires for admin saves too. ⚠ `BomOverrideHistory` has **no actor
   column** (`PriceHistory` has `changed_by`) — worth a follow-up if you want "who changed it".
3. **#116's 3.2 m prod script had already been applied.** I reported it as outstanding for
   several turns from a stale note of my own; your dry-run surfaced the truth — all 8 rows
   `ALREADY-GUARDED`, errors 0, both bodies matched. **The rule is live on prod and always was.**
   My error, not yours.
4. **The saved-Excel byte-lock was retired by design** (R7 waived byte-stability), replaced with
   structural assertions. If anyone expects `REGRESSION_NHASH` to still exist, it does not.

## Open items

- **Customer sends — CLOSED by your ruling:** "no quotes in this format will be sent to
  customers." Recorded as the permanent position, not a temporary safety measure. Customer
  quotes continue via download-and-attach or the templated `/results/{id}/report` PDF.
- **Nadie's user account has no email address** (`email = ''`; same for `kenny` and `user`).
  Her sends work, but the sender-Cc silently won't reach her until that field is filled in.
  One-field admin fix.
- **Calculator 2 shows the 3.2 m zeros with no red notice** — carried over from #116, not mine,
  still open.
- **`BomOverrideHistory` actor column** — see premise correction 2.
- **CA-run prod deploys** still blocked on sudo password by design; unchanged.

## Process notes

- **Ops commands must be written for the account that runs them.** The `journalctl` line I gave
  you failed because `icb` is in `icb sudo users` — **not `adm`/`systemd-journal`** — so journald
  showed only its own messages. `mickeyger` *is* in `adm`, which is why it worked for me. Prefix
  with `sudo` for anything run as `icb`.
- **Never byte-compare two OOXML renders.** python-docx/openpyxl hand each part to
  `zipfile.writestr`, which stamps entries with the wall clock at **2-second granularity** — so
  identical documents differ whenever two renders straddle a bucket. It passes locally and fails
  on the slower Windows CI leg. Use a normalized digest over member names + decompressed bytes.
  Cost one CI cycle.
- **A concurrency test that has never been seen red is worthless.** For #120 I removed the lock
  and confirmed all three tests fail, then restored it. Recommend that A/B for any future
  race-condition fix.
- **`select_option` → `loadBOM` is one-shot** in the costings embed, and the live-calc silently
  no-ops on an empty BOM — a fill that races the fetch never calculates. Cost two Windows CI
  cycles with a different test red each run. Journeys now re-select until a BOM row renders.
- **Only some journeys are base-aware.** Bare `admin_session(page)` dials hardcoded `:8000`, so a
  side-port run gives false failures that look exactly like a broken SPA. CI passes because it
  runs on :8000. Scope side-port runs to base-aware files, or run the full suite on :8000.
- **Merge-order collision handled as predicted:** #116 landed between my PR and its merge and
  conflicted in `exports.py` exactly at the seam I flagged. Its red 3.2 m notice now rides
  *inside* the PDF cover block, so it stays on page 1 with the totals it explains — pinned by a test.
