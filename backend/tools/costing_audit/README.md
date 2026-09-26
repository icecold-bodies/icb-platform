# Costing audit — Excel ↔ MES parity packs (v1.57)

Proves, per body / per section / per scenario, that the MES calculator agrees
with Burt's `GRP Costings 2018.xlsx` — across a sweep of length / width /
height and insulation / door / foam variants — with a tolerance, a line-level
drill-down on every variance, and a CI gate so the calculator cannot drift
silently.

```
backend/tools/costing_audit/            the tool (python -m tools.costing_audit …)
backend/tests/costing_audit/packs/      packs — what to compare (YAML, user-edited)
backend/tests/costing_audit/golden/     Excel-side results per pack (JSON, committed)
backend/tests/costing_audit/mes_snapshot/  MES master data per pack for CI (JSON, committed)
backend/tests/costing_audit/sheet_maps/ overrides for odd sheets
backend/tests/costing_audit/accepted_differences.yaml
.github/workflows/costing-audit.yml     the CI gate
```

Burt's workbooks **never enter git** (`tests/costing_audit/.gitignore` ignores
`*.xlsx` / `*.xls`; `test_packs_and_rules.py` asserts it). Only golden JSON does.

## What is compared

Each section's **material cost as the sheet computes it** — the gated J-column
total (`J51 = I51*H51`, `J122 = H122*2` for two sides), summed over every gated
cell between one section label and the next (which is exactly what Burt's
`GRAND TOTAL =SUM(J..)` adds, and what carries the second PU-gated row under
each door section). Not the raw `=SUM(H..)`, not selling price; margin and
ratio are out of scope.

On the MES side the same scenario goes through `_build_bom_items →
calculate_bom` — the code path `/api/calculate` runs — and the section is
`category_totals[<MES section>]`. Sections match by **name** (normalised: case,
spacing, `&`/`+`, token order — `DOOR FITTINGS SRD` = `SRD DOOR FITTINGS`),
never by position. Excel's two bare `DOOR FITTINGS` labels take their door
section's prefix.

`variance_pct = |mes − excel| / |excel|`, default tolerance 1.0 % (per pack,
per run). One side zero and the other not is a **PRESENCE** flag, never a
division.

| status | meaning |
|---|---|
| PASS | both priced, within tolerance |
| FLAG | both priced, over tolerance → line triage |
| PRESENCE | one side zero/absent (`MISSING_IN_MES`, `EXTRA_IN_MES`, `EXTRA_SECTION_IN_MES`) |
| SKIP | both zero (the rear door not fitted, …) |
| UNVERIFIABLE | Excel cannot price it: `STALE_LINK` (missing 2004 price file), `ERROR_CELL`, `NO_4G_REFERENCE` (PU rate hard-coded, no 4G spelling), `EXCEL_NO_PRICE:EPS` (the insulation's price cell is empty) — never PASS |
| UNMAPPED | Excel section with no MES section of that name |
| ACCEPTED / EXPIRED | covered by `accepted_differences.yaml` — `kind: known_defect` (amber; diagnosed, tracked, awaiting a work order — the entry list IS the WO list) or `kind: tolerated` (grey); expired = past `review_by`, fails |
| NO_GOLDEN | the pack has a scenario the golden lacks — re-run `audit golden` |

Line triage pairs lines by normalised description (duplicates in order,
leftovers by prefix: Excel `130*62MM TAPPING BLOCKS` ~ MES `…_200MM` +
`…_250MM`), classifies `MISSING_IN_MES`, `EXTRA_IN_MES`, `PRICE_DIFF`,
`QTY_DIFF`, `BOTH`, `GROUP_DIFF`, `STALE_LINK`, and names the largest rand
contributor as the likely cause. A MES line whose quantity formula carries a
literal `×0` is tagged **ZERO_FORMULA**.

## Variants (per body, per pack)

`as_sheet` (Burt's flag/thickness block exactly as saved) · `all_eps` ·
`all_pu` · `srd` · `drd` · `foam_4g` · plus `custom_variants` spelled per
panel (`FRONT: pu:0.05`). Thickness for `all_eps`/`all_pu` comes from the
sheet's own block where non-zero, else the pack's `thickness_defaults`.

`gate_mode` (pack or body): `as_sheet` (default — every sheet has an EPS-gated
and a PU-gated row per door section, so honest flags price PU doors), `force`
(the door's gate cells written 1/0 by door type), `eps_flag` (EPS flag Y with
thickness 0 when the panel is PU).

PU foam grade is a controlled substitution of the price-list reference in the
PU lines (`[1]PU!$C$17` = 32D, `$C$19` = 4G) — Burt's own manual edit. Sheets
saved on a mix are normalised and the mix is recorded as a finding. Sheets
that hard-code a rate (`*3090/2.98`: the three chillers, DRY FREIGHT, Adv
Vacuum) cannot express 4G → `NO_4G_REFERENCE`.

## Local prerequisites

* LibreOffice (proven with 26.8.0.3). Resolved as `--soffice PATH` →
  `$COSTING_AUDIT_SOFFICE` → `PATH` → `C:\Program Files\LibreOffice\program\soffice.exe`
  (Windows) / `/Applications/LibreOffice.app/Contents/MacOS/soffice` /
  `/usr/bin/soffice`.
* The three workbooks in one folder: `GRP Costings 2018.xlsx`,
  `PRICE 2017 MARCH.xlsx`, `FORMULAS 2018.xls` (adjacency resolves the `[1]`/`[2]`
  links). Read-only: every scenario is an openpyxl copy in a scratch folder.
  The GRP file may be open in Excel — the saved file is what is read.
* `backend/.env` pointing at the dev database for a live `audit run`.

## Commands

```
cd backend
python -m tools.costing_audit discover --workbook-dir DIR [--sheet NAME]...
python -m tools.costing_audit golden   --pack P --workbook-dir DIR
python -m tools.costing_audit run      --pack P [--tolerance X] [--out DIR]
python -m tools.costing_audit run      --pack P --live-excel --workbook-dir DIR
python -m tools.costing_audit run      --pack P --env prod          # prod's accepted list
python -m tools.costing_audit reaccept --report R.json [--env prod] # re-evaluate a saved run
python -m tools.costing_audit snapshot --pack P [--pack Q ...]
```

* **discover** prints the auto-detected cell map per sheet (inputs, flag
  block, sections with header/TOTAL rows, gated cells and the flags each gate
  reads, a self-check that the section sum equals the GRAND TOTAL). Odd sheets
  get a `sheet_maps/<slug>.yaml` (`sheet`, `label_col`, `rename`, `ignore`).
* **golden** recalculates every scenario of the pack (one LibreOffice call per
  40 copies) and writes `golden/<pack>/<sheet>.json` + `_manifest.json`
  (workbook sha256 fingerprints, date, pack fingerprint, workbook month).
  Before trusting anything it recalculates a *null* scenario per sheet and
  requires it to reproduce Excel's own cached totals (prove-then-trust).
* **run** costs the golden's scenarios through MES and writes
  `costing_audit_<pack>.html` (self-contained, no CDN: matrix bodies ×
  scenarios → section table → line triage), `.csv`, `.json` and a Markdown
  summary; exit 1 on any unaccepted FLAG. `--base-url http://127.0.0.1:8011`
  posts to a side-port server instead (never :8000). `--mes-snapshot` loads
  the pack's MES snapshot first (refuses a non-`_test` database).
* **reaccept** re-applies an accepted list to a saved report JSON and rewrites
  the HTML/CSV/JSON/MD — no MES, no database. This is how a run made on the
  prod VM is re-evaluated on a laptop after the prod list changes.
* **snapshot** exports the calc-path rows the packs' bodies need (trailers,
  BOM, materials, sections, recipes, formulas, global variables, the 4G
  factor) from the dev database for CI; several `--pack`s make one
  `mes_snapshot/all.json`.

### Accepted differences: per environment, tied to a mechanism

`accepted_differences.yaml` is the **dev** baseline; `accepted_differences.prod.yaml`
the **prod** one (`--env prod`, or `--accepted PATH`). The two databases have
drifted apart — prod matches Burt where dev does not and carries defects dev
does not — so one list cannot describe both. Every entry may carry `cause:`
(a string or list; case/space-insensitive substring of the cell's reason or
likely cause): the acceptance then only greys cells failing for THAT
mechanism, and a cell in the same section failing for another reason stays a
FLAG. Without it the first prod run hid a R23k SRD PU error behind a R60
tapping-block entry.

### Running the audit on prod

Prod's Postgres is not exposed, so the run happens on the VM, read-only,
under `/tmp`, with prod's own app code and database — nothing under
`/opt/icb-platform` changes and nothing is a deploy. Stage the tool + tests
folders and a `pip install --target /tmp/icb-audit-deps PyYAML` beside them,
then (the DB-touching part is the operator's paste):

```
set -a; . /etc/icb/backend.env; set +a
cd /tmp/icb-audit/backend
PYTHONPATH=/opt/icb-platform/backend:/tmp/icb-audit-deps /opt/icb-platform/.venv/bin/python   -m tools.costing_audit run --pack chillers --env prod --out /tmp/icb-audit-reports-prod
```

Copy the reports back; `reaccept --env prod` re-evaluates them later without
another prod run.

## Burt issued a new sheet — three steps

1. Put the new `GRP Costings 2018.xlsx` (and PRICE / FORMULAS if they moved)
   in the workbook folder; set `workbook_month` in the packs.
2. `python -m tools.costing_audit golden --pack smoke --workbook-dir DIR`
   (then chillers, freezers, icecream). Read the prove-then-trust line and
   the findings.
3. `python -m tools.costing_audit run --pack smoke` locally, then commit the
   golden JSON (+ a refreshed `snapshot` if the MES BOM changed). CI compares
   MES against the golden from then on and warns when a pack names a newer
   workbook month than its golden.

Adding a body: copy a `bodies:` entry in a pack (exact sheet spelling from
`mapping.py`), pick lengths inside the sheet's band, run golden.

## CI

`.github/workflows/costing-audit.yml`: on PRs touching the engine, the
calculator router, the BOM models, migrations or the tool → the **smoke** pack
against the committed golden and MES snapshot, report uploaded as an artifact,
summary on the job page, fail on unaccepted FLAG. Nightly + manual → every
pack. CI never needs Excel or LibreOffice. Because the MES side in CI is the
committed snapshot, CI is an **engine-drift** gate; a local `run` against the
live dev database is the **data-drift** check.
