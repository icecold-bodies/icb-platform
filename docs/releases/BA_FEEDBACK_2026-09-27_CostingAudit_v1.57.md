# BA feedback — CA session 25–27 Sep 2026: Costing audit (Excel ↔ MES parity), first prod runs, Phase 2 request

**Lanes (all squash-merged to `backport/v1.39-base`):**

| lane | PR | merge commit | what |
|---|---|---|---|
| v1.57 `feat/v1.57-costing-audit` | #191 | `a6821d5` (25 Sep) | the audit tool, CI gate, September golden, first dev run |
| v1.57.1 `feat/v1.57.1-explosive-pack` | #192 | `712f31b` (26 Sep) | explosive pack, cause-tied acceptance, per-environment lists, offline re-evaluation, first prod run |
| v1.57.2 `feat/v1.57.2-report-layout` | #193 | `b4d2dc8` (27 Sep) | report layout Michael asked for; an acceptance must explain the whole difference |

**Base is now `b4d2dc8`.** CI was green on the exact merged head of every PR (the `CI` matrix and the new
`Costing audit` check). **No prod code deploy, and none was needed** — every lane is a backend tool, tests, a CI
workflow and docs; no app code, no migration, no `?v=` bump. **Prod stays on `6b77d52`.** Prod was *audited*
(read-only, from `/tmp` on the VM, via Michael's sudo paste) on 26 and 27 Sep. Michael made prod **data** fixes on
the chiller bodies on 27 Sep based on those audits. **No release tag cut — BA-coordinator's call.**

**Michael's ask for next:** Phase 2 — the audit as an **admin feature, run on demand** (§7).

---

## At a glance

| | |
|---|---|
| **Built** | `python -m tools.costing_audit discover · golden · run · reaccept · snapshot` — LibreOffice oracle over Burt's workbook, MES probe on the real `/api/calculate` path, section + line comparison, self-contained HTML/CSV/JSON/Markdown reports, CI gate |
| **Coverage** | 12 bodies in 5 packs: smoke (18 scenarios), chillers (84), freezers (54), icecream (48), explosive (54) — L × W × H sweeps × 6 variants (as saved, all EPS, all PU, SRD, DRD, 4G foam) |
| **Largest live-quote error found** | **PROD: a single rear door's PU costs ≈ R24.4k on every body** (raw R4 100 rate × sheets; Burt R1.5k) — **+R23k per SRD quote** |
| **Fixed on prod by Michael (27 Sep, data)** | CHILLER 2.3 METER PU panels · CHILLER LARGE PU panels + double-rear-door PU + single-rear-door EPS & fittings · CHILLER MEDIUM single-rear-door fittings |
| **Introduced on prod 27 Sep, not yet fixed** | CHILLER 2.3 METER single-rear-door fittings now carry **2 door sets and 4 hinges** (Burt 1 and 2): **+R800 per SRD quote** — still present at the 08:26 UTC re-run |
| **State** | Dev (27 Sep): 5 packs, 0 unaccepted. Prod: freezers / icecream / explosive 0 unaccepted (26 Sep runs, re-evaluated under v1.57.2); chillers 3 FLAG at 08:26 UTC 27 Sep (the item above). 22 dev + 20 prod accepted entries, all `known_defect`, all `review_by 2026-10-31` |
| **Needs a decision** | 4 rulings for Burt (§4) · dev ↔ prod data drift (§6) · 5 Phase 2 defaults (§7) |

---

## 1. What was built

### 1.1 v1.57 — the audit (#191)

The BA's recipe, extended: openpyxl writes each scenario into a **copy** of Burt's workbook, LibreOffice headless
recalculates a batch of copies (PRICE + FORMULAS adjacent), and each section's **gated** material cost is read
back. Burt's workbooks never enter git; only the golden JSON does.

- **Prove-then-trust built in.** Before any golden is written, a null scenario per sheet must reproduce Excel's
  own cached totals — it does, to 5e-10, on every sheet.
- **Section total = the sum of every gated J cell** between one section label and the next — exactly what Burt's
  `GRAND TOTAL =SUM(J..)` adds. Discovery self-checks that sum against each sheet's grand total.
- **MES side** runs the same `_build_bom_items → calculate_bom` path as `/api/calculate`, in-process, with the
  scenario spelled exactly as the calculator spells it (read off a real saved costing).
- **Comparison.** PASS / FLAG / PRESENCE / SKIP / UNVERIFIABLE / UNMAPPED / ACCEPTED / EXPIRED per section; every
  difference drills to its lines (MISSING_IN_MES, EXTRA_IN_MES, PRICE_DIFF, QTY_DIFF, BOTH, GROUP_DIFF), with the
  largest rand line named as the likely cause and a `ZERO_FORMULA` tag on MES formulas with a literal `×0`.
- **CI gate** (`.github/workflows/costing-audit.yml`): the smoke pack on every PR that touches the engine, the
  calculator router, BOM models, migrations or the tool; all packs nightly and on demand. CI has no ICB database,
  so it loads a committed MES snapshot into `icb_test` — **CI is an engine-drift gate**; a local run against the
  live database is the data-drift check.
- **Negative control** in the suite: a 5 % price error injected into a fabricated MES line is flagged and named
  PRICE_DIFF on that line; removed, it passes.

### 1.2 v1.57.1 — mechanisms, environments, prod (#192)

- **Explosive pack** (3 bodies, 54 scenarios) with its golden.
- **Acceptance tied to a mechanism** (`cause:` on every entry). The first prod run showed why: a R60 tapping-block
  entry was greying a **R23k** SRD PU error in the same section.
- **One accepted list per environment** — `accepted_differences.yaml` (dev) and `.prod.yaml`. Prod's BOM data is
  not dev's: on 26 Sep, 404 of 1 074 chiller cells differed between the two.
- **`audit reaccept`** re-evaluates a saved report against a list with no MES and no database — how a run made on
  the prod VM is re-read on a laptop.

### 1.3 v1.57.2 — the layout Michael asked for, and a stricter rule (#193)

- **Report layout.** Top half (scrolls up/down): per body, one row per L × W × H, the six variants as columns — no
  more scrolling right. Bottom half (fixed): the clicked scenario's sections on the left, the selected section's
  lines on the right (`qty × price = total` per side, differing lines first, the MES formula under each line). A
  draggable divider, remembered per browser. The page opens on the first unaccepted difference. Checked in the
  browser (clicks, drag, persistence, no console errors).
- **An acceptance must explain the whole difference.** On a flagged section, the lines named by the accepted
  entries must account for the section's net difference within tolerance, or the cell stays red with the
  unexplained remainder in its reason. Premise checked first: on all 737 flagged cells, net difference = sum of
  line differences to within R0.03. Renamed lines now pair up (`130*62MM TAPPING BLOCKS` ~
  `TAPPING BLOCKS_200MM + _250MM`). This surfaced the §3 and §4 items the older rule had greyed over.

**Tests:** 41, all green. Tool README: `backend/tools/costing_audit/README.md`. Findings record:
`docs/audit/costing_audit/2026-09/README.md` (dev reports, prod reports under `prod/`).

---

## 2. How the audit runs today

| where | how | what it proves |
|---|---|---|
| **CI** | automatic: smoke on calculator PRs; all packs nightly / on demand (Actions → *Costing audit*) | the engine hasn't drifted against the committed golden + snapshot |
| **Michael's clone (dev)** | `cd backend && python -m tools.costing_audit run --pack chillers` (~10 s) | live dev data vs Burt |
| **Prod** | Michael's sudo paste on the VM: `sudo bash /tmp/icb-audit-chillers.sh` (tool staged under `/tmp`, prod's own code and database, read-only); the CA pulls the JSON and re-renders it | live prod data vs Burt |
| **New workbook from Burt** | Michael's laptop only: `audit golden` (LibreOffice + the three workbooks), commit the JSON | the golden itself |

The prod path is a workaround: the CA's own prod execution is blocked by the session classifier, so every prod run
needs Michael at the VM. **Phase 2 (§7) removes that.**

---

## 3. Findings — PROD (live quotes), ranked by rand impact

All tracked in `accepted_differences.prod.yaml` as `known_defect` (amber) until fixed; delete an entry when its fix
lands and every later run enforces it.

1. **[MES] Single-rear-door PU on every body ≈ R24.4k** (`1.22*2.44*2` sheets × R4 100) where Burt has R1.5k —
   **+R23k per SRD quote**, chillers, freezers, icecream and explosive alike. **First work order.** Worth checking
   recent SRD quotations issued from prod.
2. **[MES, new 27 Sep] CHILLER 2.3 METER — SRD DOOR FITTINGS: SB 51111 DOOR SET ×2, CSLB HINGES ×4** (Burt ×1, ×2)
   — the double-door quantities copied onto the single door during the 27 Sep edit: **+R800 per SRD quote**.
   Not yet corrected at the 08:26 UTC run. Fix: Body Templates → CHILLER 2.3 METER → SRD DOOR FITTINGS, formula
   `4` → `2` and `2` → `1`. Deliberately **not** accepted — it's the only red on prod.
3. **[MES] ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8: +R13k–R27k** per quote; Burt's
   sheets have no such line. On ICECREAM UP TO 4.8 the floor also lacks Burt's `12MM PF PLYWOOD` (−R2.5k) —
   consistent with the ALU floor option replacing the plywood floor; confirm in prod's Body Templates.
4. **[MES] CHILLER MEDIUM PU panels (all-PU quotes)**: the front's new formula `1.22*2.44*{FRONT PU}` is missing
   `*2` (half-priced, −R551); sides +R4.3k, roof and floor +R4.4k each — not yet aligned like CHILLER 2.3 / LARGE.
5. **[MES] ICECREAM 4.9 UP has the length 6.7 hard-coded** in its ROOF, FLOOR, ALUMINIUM, SUB FRAME and REFLEXITE
   formulas (SIDES is correct on prod): every quote is priced at 6.7 m whatever length is entered.
6. **[MES] CHILLER MEDIUM double-rear-door `2317 DOOR RUBBER` quantity `×0`** (−R672).
7. **[DATA]** icecream rear doors carry a `3MM ALU BUFFER PLATE` Burt doesn't (+R494); explosive bodies carry
   `6MM PF PLYWOOD` where Burt has 4MM, and EXPLOSIVE 4.9 AND UP prices PU at 12.08 × R234 vs Burt's 2.98 × R172
   (+R370 to +R1.5k per panel); FREEZER 2.3 METER roof/floor PU +R1.1k per panel; FREEZER LARGE sides sized from
   width instead of height (+1.2 %); single-rear-door fittings prices (hinges at the pair price per hinge,
   silicone ×2) on most bodies; small bracket / plate items.

**Where prod is closer to Burt than dev:** tapping blocks, the 1MM galv plate, the 3MM 3CR12 floor plate price,
the LVL beam rule, ICECREAM 4.9 UP's sides, and — after 27 Sep — the chiller PU panels on CHILLER 2.3 / LARGE.

## 4. Rulings needed from Burt (via Michael)

1. **Rear frame + floor plate on single-rear-door bodies.** Burt's sheets gate the section on the double-door
   flags, so an SRD body carries R0 there; MES always includes it (R2.4k–R5.5k). Which is right?
2. **Chiller PU rate.** Burt's three chiller sheets hard-code `*3090/2.98` — not linked to the price list, whose
   September 32D price is R4 100. On 27 Sep Michael aligned prod's CHILLER 2.3 / LARGE PU to Burt's sheet, so prod
   now matches the sheet — **but both may be ~25 % under the current foam price.** Burt to confirm the chiller rate
   and, ideally, link those sheets to `[1]PU!$C$17` like the other bodies.
3. **CHILLER 2.3 double rear door, PU:** Burt's sheet charges the door's EPS line (R432) even when the door is PU
   (the line has no insulation gate), so it prices EPS and PU together. MES charges PU only.
4. **Single rear door inner skin:** Burt's SRD sections carry 4MM PF PLYWOOD and a GLUE LINE at R0 (cells
   hard-coded 0); MES charges them (+R480–R590). Does a single rear door get the plywood skin?

## 5. What went wrong in this session, and what it changed

- **My first §3.0 report was wrong.** I said Burt's all-PU sheets price the double-door sections at zero — I had
  read only the TOTAL row and missed the PU-gated row below it. The discovery self-check (section sum = GRAND
  TOTAL on every sheet) exposed it before anything was built on it.
- **A too-loose acceptance hid real errors twice** (a R60 entry over a R23k PU error; then over a missing EPS line
  and R480 of plywood). Fixed in two steps: acceptance tied to a mechanism (v1.57.1), then required to explain
  the whole difference (v1.57.2).
- **CI crashed on its first run** — a 2 450-row insert exceeded Postgres's 65 535 bind-parameter limit (the smaller
  local snapshot hadn't). Inserts are chunked; the loader is now tested every PR inside a rolled-back transaction.
- **I removed a migration-seeded row from the shared `icb_test`** while cleaning up a snapshot trial
  (`costings.pu_foam_4g_factor`, deleted by natural key after an `ON CONFLICT DO NOTHING` load had skipped it).
  Restored to migration 0046's seed value the same hour; test loads now roll back instead of committing.
- **A redirected Windows console turned finished runs into exit 1** on a "⚠" character — fixed.
- **Prod access:** the classifier blocked the CA's prod execution after the first file staging, so every prod run
  has been Michael's paste. Correct behaviour for prod; the reason Phase 2 matters.

## 6. Dev ↔ prod data drift — decision needed

Michael's 27 Sep fixes were made **on prod only**. Dev still has the chiller PU `×0` formulas, the CHILLER 2.3 /
LARGE double-door PU at the raw rate, and differs from prod on tapping blocks, galv plate and more (on 26 Sep, 404
of 1 074 chiller cells differed). Dev-side lanes and CI's committed snapshot therefore describe a different BOM from the one
quotes are priced on. **Recommendation:** a small data WO to mirror the corrected prod rows into dev (or refresh
dev's BOM tables from a prod dump), then regenerate the CI snapshot and prune the dev list. BA to decide.

---

## 7. Phase 2 request — "Costing audit" as an admin feature (Michael)

**Goal.** An admin can run the audit on demand from the MES — no terminal, no VM paste, no CA — see the report
in the page, and see what changed since the last run (which is how Michael used it on 27 Sep: fix, re-run,
compare).

**Proposed scope (recommended defaults — ratify or change):**

1. **Page:** Admin → **Costing audit** (`/admin/costing-audit`). Pick a pack (smoke, chillers, freezers,
   icecream, explosive, or all) → **Run** → progress → the report shown in the page in the v1.57.2 layout, with
   HTML and CSV download.
2. **Runs against the database the server is on**, in-process, read-only — so on prod it audits prod. The
   accepted list is chosen by environment (prod list on `icb_platform`, dev list otherwise), shown on the page.
3. **History:** each run stored (who, when, pack, environment, counts, pass/fail) with a **"changed since the
   previous run"** summary (cells that moved, and how). **Default: a new table `costing_audit_runs`** (summary +
   gzipped report JSON; the HTML is rendered from it) → **migration 0049**, collision-checked at build time.
4. **Execution:** a background job per run with a database lock so only one audit runs at a time across the four
   prod workers (~10 s per pack, ~45 s for all); the page polls for status.
5. **Access:** admin only, behind a catalogue permission (`admin.costing_audit`) so it can be granted to others
   later without code.

**Out of scope for Phase 2 (by ratified default):**
- **Generating golden stays on Michael's laptop** — it needs LibreOffice and Burt's workbooks, which by ruling
  stay off the server. A new workbook still means: `audit golden` locally → PR → deploy.
- **Editing accepted differences in the page** (Phase 3 candidate); lists stay in the repo, reviewed in PRs.
- **Scheduled prod runs** (e.g. nightly, emailed summary) — Phase 3 candidate.

**What the lane involves:** router + template (reusing the report writer and `mes_probe`), the runs table and
migration, the permission catalogue entry, a journey test for run → report, PyYAML into prod's venv (already in
`requirements.txt`). **This will be the first prod code deploy of the audit tool**, so it goes through the usual
release ops (fresh CA, deploy kit, `/openapi.json` + served-bytes proof). Estimate ~1.5–2 days including the
journey test and deploy.

**Decisions for the BA (Y/N):**
1. Store runs in a DB table with migration 0049 (recommended), rather than as files on the server?
2. Admin-only, via a grantable permission (recommended)?
3. Keep golden updates as a repo PR (recommended), rather than an upload in the page?
4. Include "changed since previous run" in Phase 2 (recommended — it's Michael's actual workflow)?
5. Scheduled nightly prod run with an emailed summary — Phase 3 (recommended), or now?

---

## 8. Housekeeping

- **VM:** the staged tool and reports under `/tmp/icb-audit*` can go after Phase 2 ships (or now:
  `sudo rm -rf /tmp/icb-audit /tmp/icb-audit-deps /tmp/icb-audit-reports-prod* /tmp/icb-audit-run.sh /tmp/icb-audit-chillers.sh`).
- **Michael's clone:** a `costing-audit-reports-8013` entry was added to `.claude/launch.json` (git-ignored; a
  static server on :8013 for checking report pages in the in-app browser). `:8000` untouched throughout.
- **Review date:** every accepted entry expires on **2026-10-31** — after that, uncorrected items turn red in every
  run (by design), so the defect list gets re-reviewed rather than forgotten.
- **Not in these packs yet:** TAUT LINER RIGID and BAKERY BODIES (different sheet layout — need a sheet map), the
  Manni bodies, Adv Vacuum / Advantica / Chester / meat / dry-freight / GRP / Rhinorange bodies (packs can be
  added by copying a `bodies:` entry — README shows how).
