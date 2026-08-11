# BA Feedback — Validated References (v1.45 → v1.46.3)

**Date:** 11 August 2026
**Requested by:** Nadie (Internal Sales), ratified by Michael
**Status:** ✅ **SHIPPED and LIVE ON PROD** — `cfc7480`, tagged **`v1.46.3`**
**Prod:** `https://192.168.0.251/mes-app/` · deployed 11 Aug 10:37 SAST · migration **0039** applied
**PRs:** #121 (feature), #122 (economy + a correctness fix), #123 · #124 · #125 (correctness)
**Not built, by design:** the nightly cross-reference drift report — Phase 2, separate WO

---

## 1. What Nadie asked for, and what she now has

> When a costing balances with her Excel (or is approved), Nadie marks it as a validated
> reference with a friendly label. Later she recalls it as a starting point, and whenever a
> live costing exactly matches a reference's configuration but the manufacturing cost has
> drifted beyond tolerance, the system warns her.

All four behaviours are live:

| Behaviour | Where | Notes |
|---|---|---|
| **Mark** | "★ Mark as validated reference", under **Approve & Save** in the calculator's summary panel | Label prompt pre-filled `"{body type} {L}x{W}x{H}"`. Also on the MES costing-detail page for **Accepted** costings. |
| **Recall** | A second dropdown **directly below Body Type**, shown only when that body type has active references | Lists label · dims · validated date. Picking one loads the full configuration and notes "loaded from reference {label}". |
| **Warn** | After every recompute | Exact configuration match + drift beyond tolerance → red banner with the %, both totals, and the **categories that moved**. Within tolerance → a quiet green tick. No match → nothing. |
| **Retire** | "Manage" beside the dropdown | Soft retire — stops matching, leaves the dropdown, row kept for the record. Admin tolerance field lives here too. |

**Design principle held:** a reference is a **thin pointer** — label + fingerprint against the
existing saved costing. No costing data is copied, and recall always **copies**, so a
reference's own record is never edited.

### Permissions
New catalogue key **`costings.validated_refs_manage`**, seeded **{admin, full}** — the same
pattern as `costings.price_master_edit`, so Nadie's role owns her own reference library.
Creating and retiring need it; **reading, recalling and the drift warning need nothing beyond a
costings login.**

### Admin knob
**Reference tolerance %** — default **2%**, tunable from the Manage panel (admin only). Stored in
the generic `admin_settings` store rather than as a pricing global variable, so it never enters
the formula-evaluation namespace.

---

## 2. Michael's usability changes (#122)

Raised from testing: the parameter panel and summary footer were squeezing the category totals.

| | before | after |
|---|---|---|
| Body Type Parameters block | 485 px | **348 px** |
| Summary footer (no banner) | 204 px | **115 px** |

- Every caption now sits **left of its field** on one line, instead of stacked above it.
- **Total Cost** caption and amount on one line.
- **Removed:** the "Selling Price" sub-line, and the unused **Print** and **Full Report** buttons.
- ~187 px handed back to the category totals.

**Deliberately kept:** the sub-line under Total Cost still exists but renders empty — it is the
only thing that explains a **discounted** total ("Was X · less Y discount"). **Calculator 2 keeps
its Print / Full Report buttons** (it shares the same JavaScript file; the toggles were made
tolerant of the buttons being absent rather than changed in both places).

---

## 3. Four correctness problems found during testing — and what each teaches

Every one was found by Michael using it or by verifying the deploy, and **every fix is pinned by
a test proven to fail without it.**

### 3.1 A reference never matched a fresh browser (#122)
**Symptom:** "the function is not working" — the dropdown appeared but the drift warning never
fired.

**Cause:** the optional-**EXTRAS** selection is held in the **browser's localStorage**, not on the
costing. It was part of the reference's identity, so a reference marked with extras enabled could
only ever match a browser that happened to share that localStorage state.

**Fix:** extras removed from identity. Identity is now **server-side, costing-borne facts only** —
body type, dimensions, body options, excluded categories, insulation flags, insulation
thicknesses.

**Trade-off Michael accepted:** two costings of the same body differing *only* in extras now share
an identity, so the extras' cost surfaces as **drift** rather than as "no match". That is the price
of matching reliably.

> **Lesson for future requirements: never derive a stored identity from browser-local state.**

### 3.2 A reference attached itself to the wrong body type (#123, #124)
**Symptom:** marking a FREEZER MEDIUM costing produced no dropdown under FREEZER MEDIUM.

**Cause:** the write had succeeded — onto the **wrong body**. The real row read
`label = 'FREEZER MEDIUM 5.6x2.5x2.4'` against **CHILLER LARGE**. The mark action bound to the
last saved (or last opened) costing, and that binding **survived a body-type switch**.

**Fix, in two steps and worth reading as one lesson:** #123 guarded the *saved-costing* path but
explicitly exempted the *edit* path on the reasoning "opening a costing for editing selects its own
body type" — true at load, false the moment the dropdown changes. Verifying the deploy caught it
the same hour. #124 replaced both client-side guards with **one authoritative server check** at
mark time: the costing is fetched and its body type must agree with what is on screen. That covers
saving, editing and restored sessions and cannot drift out of sync.

> **Lesson: when a fix special-cases one of two symmetrical pieces of state, the exemption is
> usually wrong for the other one too. And "the UI isn't showing X" can be a write that landed on
> the wrong parent — read the actual row before treating it as a display bug.**

### 3.3 The label didn't follow the length (#125)
**Symptom:** a reference labelled `5.6` whose record was `5.3`.

**Two distinct findings, and they matter separately:**

1. **The deployed code was already correct.** The bad row came from a **browser tab still running
   the pre-fix JavaScript** — open since before that morning's deploys. Cache-busting only takes
   effect when the page is re-fetched; an open tab keeps executing what it loaded. Proven by a
   discriminating test on the live build (typed 9.9 on screen → the prompt still offered the
   record's 5.3). **Remedy: hard-reload after a deploy.**
2. **A real gap it exposed:** dimensions feed the fingerprint, so they are *identity* exactly like
   the body type. Marking after typing a new length labelled one configuration while pointing at
   another. Changed dimensions now trigger the same **"Save first"** refusal as a changed body type.
   Margin, ratio and price overrides deliberately do **not** — they are not identity.

### 3.4 A live warning could be silently blanked (#121)
Rapid recomputes leave several match requests in flight; a stale "no match" landing last wiped a
correct warning off the screen. The banner now ignores superseded replies.

> **Lesson: any badge or banner fed by its own per-recompute request needs a sequence guard.**

---

## 4. The operating rule this settles

**Get the body the way you want it → Approve & Save → Mark.**

Change the body type *or* any dimension in between and the mark action sends you back through
Save first — by design, so that the label, the record and the fingerprint can never disagree.

---

## 5. Two things to tell Nadie before she uses it

1. **The dropdown will not appear on prod yet.** The reference table is new and empty. It appears
   for a body type only once she has marked a costing on that body type. This is the single most
   likely "it's broken" report, and it isn't a fault.
2. **The calculator looks denser** and Print / Full Report / Selling Price are gone from the
   summary panel. Nothing about pricing, saving or quote numbering changed.

---

## 6. Assurance

- **Backend:** 36 unit tests — fingerprint stability and tick-order invariance; every identity
  field proven to separate configurations; extras proven **not** to; the exact "fresh browser"
  regression; tolerance boundary (1.9% quiet, **2.0% inclusive**, 2.1% warns, symmetric on the
  downside); permission gates on create/retire/tune; retired references never match; a pre-v1.39.9
  costing with no configuration snapshot refused loudly rather than stored under a near-empty hash.
- **Journeys:** the full loop in one browser session — mark → recall (totals identical + green
  tick) → price bump → red warning with category deltas → retire → gone; plus a geometry-based
  density check, the mis-attach guards on both binding paths, and a naming-isolation check that the
  unrelated admin **BOM Snapshots** feature is untouched.
- **CI:** green on both Linux and Windows on the exact head SHA of every one of the five PRs.
- **A new diagnostic tool:** `MES_JOURNEY_CPU_THROTTLE` throttles the browser so slow-CI-runner
  failures reproduce locally in one run instead of one push. Three CI-only reds paid for it, and it
  immediately exposed two real races invisible at full speed.

## 7. Data and rollback position

- Migration **0039** is additive and guarded: a new table, a partial unique index, one settings
  row. No existing table, column or row was altered.
- Fresh prod backup taken **before** the migration: `icb_platform_20260811-1035.dump.gz`.
- **Code-only rollback** to `f4b1e1d` is safe and leaves 0039 in place, unused. A schema rollback
  (`alembic downgrade 0038`) would **drop any references Nadie has created** — prefer the code-only
  path unless the table itself is the problem.
- Naming isolation: nothing shares names, routes or wording with the pre-existing admin
  **"BOM Snapshots"** feature.

## 8. Open items for the BA

| # | Item | Owner |
|---|---|---|
| 1 | **Phase 2** — nightly drift report across all references. Not started, deliberately. | BA to schedule |
| 2 | Should **Calculator 2** get the same compact layout and footer trim? Untouched for now. | Michael |
| 3 | Should the **discount sub-line** under Total Cost also go? Kept because nothing else explains a discounted total. | Michael |
| 4 | The **2% tolerance** is a first guess. Worth revisiting once Nadie has a few weeks of real references. | Nadie / BA |
| 5 | Prod deploys need Michael's hands (repo owned by `icb`, password sudo). Fine as a control; worth a conscious decision if deploy frequency rises. | BA / Marnus |
