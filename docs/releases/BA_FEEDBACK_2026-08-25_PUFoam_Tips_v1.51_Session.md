# BA feedback — CA session 25 Aug 2026: PU foam grade, opt-in tips, v1.51 prod deploy

**Lanes:** `feat/v1.51-pu-foam-4g` (#168) and `feat/v1.51-tips-toggle` (#171), both squash-merged to
`backport/v1.39-base`. **Prod deployed 25 Aug 21:04 SAST at `e36482d`** (the full v1.51 bundle:
#169 + #168 + #170 + #171). Migration head `0046`. Cache-busts `calculator.js?v=173`,
`style.css?v=20`. **No release tag cut — BA-coordinator's call.**

---

## 1. Enhancements shipped

### 1.1 PU insulation foam grade — 32D PU FOAM / 4G FOAM per costing (#168, `dfadc70`)

Replaces Burt's manual workbook edit (the process that produced mixed pricing inside single
bodies) with **one explicit selection per costing** under BODY OPTIONS:

- **UI:** "Insulation foam" radio pair — `32D PU FOAM` (default) / `4G FOAM` — shown only on
  bodies that actually consume PU foam. Toggling moves every PU line and the grand total by
  exactly `5875/4310 = 1.36311`; 32D restores to the cent.
- **Persistence:** the grade freezes into the approval snapshot, returns on
  `GET /api/calculations/{id}`, restores on edit-load and on validated-reference recall. Records
  saved before this lane have no key and read as 32D — which is what they were priced at.
- **Document:** the quotation spec block gains an `INSULATION FOAM` row, printed only when the
  quote actually uses PU insulation.
- **Design decision (ratified via C4-style divergence):** the dispatch asked for "4G FOAM
  material rows per PU-using category". That does not fit the schema — materials are per
  *section* and global across bodies, so a 4G material cannot carry per-category prices; it
  would need ~100 duplicate BOM rows that go stale against their 32D siblings on every price
  update. Instead the MES stores **one price per PU line (the 32D side)** and **derives** 4G at
  calculation time. The pair ratio holds by construction for every row and survives the August
  price update untouched.
- **Tunable ratio:** `admin_settings['costings.pu_foam_4g_factor']` (= `1.363109048723898`),
  code fallback in `services/insulation_foam.py`. See open item 4.1.

### 1.2 Migration 0046 — PU price normalisation (data fix)

Classifies every PU cost row by `stored_price ÷ linked thickness` (a rate that names the grade
outright: 32D = 4305.37, 4G = 5868.69, plus Burt's 2.99-divisor typo variants; tolerance 0.1 %,
closest classes 0.335 % apart). Only recognised-4G rows are rewritten down to 32D; the 2.99 typo
is corrected on the way; everything unrecognisable is **refused and reported**, never guessed.
Every rewrite is journalled (`icb_costings.pu_foam_normalisation`) so downgrade restores prices
byte-exact. Full table: `docs/audit/v1_51_S3_1_pu_foam_classification.md`.

- **Dev:** 9 rows rewritten (Explosive 4.9+ ×4, Meat Hanger Large ×5 incl. the typo row).
- **Prod:** 4 rows rewritten (4005/3996 Explosive 4.9+ ROOF+SIDES; 5921/5910 Meat Hanger Large
  FLOOR+ROOF). **Both bodies were already MIXED on prod** — partly hand-normalised at some
  point — and are now uniformly 32D. The read-only pre-flight predicted prod's outcome
  byte-for-byte before the deploy touched anything.

### 1.3 BOM hover tips opt-in, off by default (#171, `e36482d`)

Michael's request from prod click-through: tooltips fired on every hover across the BOM.

- New **"Tips" checkbox** in the Bill of Materials header (appears once a BOM loads), unticked
  by default, remembered per user (`localStorage`).
- Governs **both** hover mechanisms: the four coloured price bubbles (override / recent /
  outdated / bulk) **and** the large hover FORMULA panel. The formula panel previously had a
  hidden page-level state defaulting to ON, changeable only by *clicking* a BOM row — an
  undiscoverable control; the Tips box now owns that state in both directions, and a stray row
  click can no longer resurrect the panel while Tips is off.
- Implementation subtleties that mattered: the price cells carry a native `title` alongside the
  CSS bubble (CSS cannot suppress a `title`, so it is not emitted while tips are off); the price
  **colour** stays either way — it is the price's status, not a tip; toggling patches the DOM in
  place because a re-render would have replaced the costed table with the pre-calc view
  (measured: 209 price cells → 0); `style.css` needed its own cache-bust (19 → 20) or a cached
  stylesheet + new JS would show no tips at all.
- Scope guard tested: section headers, buttons, and the `{NAME}` thickness-edit hints keep their
  tooltips in both states.

## 2. Fixes

| Fix | Where | Detail |
|---|---|---|
| **Duplicate `calculator.js` tag** | #170 (sibling CA) | #168 (v=170) and #169 (v=171) each bumped the same line; the merge auto-joined both tags with no conflict marker — double download + `SyntaxError: Identifier 'allCustomers' has already been declared` on every calculator load. **Root cause was this lane's discipline lapse:** the cache-bust collision check ran at discovery, not re-run at commit, and #169 landed in between. #171's busts were re-checked immediately before commit, and the one-script-tag assertion is now part of the check. |
| **0046 `AmbiguousParameter` (CI red)** | #168 second push | The guarded settings-seed put one bind in an untyped output position *and* a varchar comparison; Postgres refuses to type it. Fixed with explicit CASTs — and produced a new discipline (§3.1). |
| **Explosive 4.9+ / Meat Hanger Large mixed pricing** | 0046 on prod | Both bodies quoted part-32D/part-4G before tonight. Now uniform. |
| **Tips journey CI red** | #171 third push | Three harness faults, zero product faults: hovering a cell inside a collapsed BOM group; hovering a row the pointer already sat on (no `mouseover` fires); a staged formula of `"1"` which the formula panel *by design* never renders. All fixed and re-run locally against the new `icb_test` before pushing. |

## 3. Process notes banked (full detail in memory topic files)

1. **Dry-run migration SQL against real data in a rolled-back transaction** before pushing —
   green unit tests on a migration's classifier prove nothing about its SQL; CI must never be
   the first Postgres parser to see it. The harness now also proves seed-guard, idempotence,
   and byte-exact downgrade.
2. **Adversarial review of the prod deploy block paid for itself** (7 agents, 4 lenses): it
   caught an unasserted health probe (silent `set -e` death on refused connection; a 503 would
   have sailed to DONE) and a tautological SPA check — replaced with a served-bytes grep of the
   actual `/mes-app/assets/` bundle for a #169 marker. Both defects would have degraded the
   deploy's evidence, one could have masked a dead backend.
3. **Read-only pre-flight for data-mutating migrations** — the classifier reproduced in SQL,
   run against prod before deploying, so the outcome was known (and communicated) in advance.
   Prod differed from dev (4 rewrites vs 9); the pre-flight is why that was a footnote instead
   of a mid-deploy surprise.
4. **A uvicorn on :8000 is not necessarily the dev server** — a journey run's `live_server`
   fixture binds 127.0.0.1:8000; Michael's binds 0.0.0.0. Read the command line and parent
   before killing anything on that port.
5. `#grand-total` is **not** a cost sum (`cost × (1+margin) ÷ ratio`, ratio defaults 55 %) —
   assert money on `lastResult.grand_total`. Caught in this lane's own journey before it could
   go red against correct code.
6. `icb_test` now exists on 5432 (Michael created it mid-session) — DB-backed tests and
   journeys are locally runnable again. It sat at alembic 0045; upgrade before trusting it.

## 4. Open items

| # | Item | Owner | Shape |
|---|---|---|---|
| 4.1 | **No admin UI for the 4G factor.** Today a ratio change (32D and 4G moving differently on a future price list) is a one-line SQL as postgres. Proposed: a "PU foam 4G factor" field on an admin screen, same AdminSetting pattern as the validated-references tolerance (~1 h lane). Not urgent — the ratio has held since the 2017 list. | BA to ratify | small WO |
| 4.2 | **Rhinorange PU rate unclassifiable** (5 rows, coherent internal rate 6373.80, derived from neither sheet price). Selecting 4G there quotes 1.36311 × an already-high number. Burt to restate the rate on a known basis; 0046 is idempotent and picks it up on a re-run. | Burt | pricing decision |
| 4.3 | **`MEAT HANGER SMALL-MEDIUM / FLOOR` (bom_id 6229) is 4G-baked** (`446.02 = 327.208 × 1.36311`) but thickness-less, so invisible to the classifier. Quotes as before under the 32D default (not a regression); one price edit once Burt confirms the intended number. | Burt | pricing decision |
| 4.4 | **Prod's shared FRONT/DRD/SIDES PU material price is `352.12`** — itself a 4G-derived number — inherited by the 98 shared-default rows. 0046 correctly never touches shared prices. Data-quality item for Burt's next price pass. | Burt | pricing decision |
| 4.5 | **Three prod thickness-wiring oddities** surfaced by the pre-flight (Explosive ≤2.7 DRD, Icecream Large DRD, Icecream Medium SRD): prices are already 32D but the linked thickness disagrees with siblings, so their rates land off-grid. Cosmetic to pricing today; worth a look when Burt reviews 4.2–4.4. | Burt / BA | data check |
| 4.6 | **Release tag for v1.51** — prod is live at `e36482d`, untagged per the dispatch. | BA-coordinator | fresh-CA tag op |
| 4.7 | **Comms to Burt**: EXPLOSIVE 4.9 AND UP and MEAT HANGER LARGE now default to 32D; one click on 4G FOAM restores the old price to the cent. Should reach him before he opens either body, or the lower PU lines read as a pricing error. | BA-coordinator | Burt-primary, Deon-cc |

## 5. Verification record

- CI green on the exact head of every merged PR (#168 at `95d0e29`, #171 at `3231732`), all new
  tests RAN (backend 835 → 886, journeys 201 → 209, **0 new skips**), negative control on the
  foam resolution turned 4 tests red and green again.
- Prod verified from both sides: every deploy-block assert green (journal = 4 rows,
  `mismatched = 0`, 4 workers, 0 bootstrap failures) **and** externally — health 200, served
  `calculator.js` byte-identical to `git show e36482d` (496,931 bytes), served SPA bundle
  carries #169, tips gate live in served CSS.
- Deploy runbook + OUTCOME: `docs/runbooks/prod-deploy-v1.51.0-pu-foam-and-tips.md` (`74325a9`).
