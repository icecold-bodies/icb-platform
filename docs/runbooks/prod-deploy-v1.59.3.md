# Prod deploy: v1.59.3 (RT2 release train) — the code release, then Manifests P and D, in one window

Target: **`https://192.168.0.251/mes-app/`** and **`https://mes.icecoldgrp.online`** · repo `/opt/icb-platform`
· service `icb-backend` (`uvicorn --workers 4`) · DB `icb_platform` · BA dispatch **RT2** (one CA, one window).

> **Status: DRAFT for RT2_RETURN_2.** Every number marked **PENDING R8** comes from the mirror rehearsal on the
> read-only prod export of the 15 bodies (RT2_RULING_1 R8), which has not reached the CA yet. No prod step other
> than the R8 export runs before **RT2_RULING_2**.

| | |
|---|---|
| Prod is at | **v1.59.2 `1d9cb47`** (30 Sep 20:51 SAST), alembic **0049**, `calculator.js?v=184`, `calculator2.js?v=126`, `admin_templates.js?v=18`. Data on prod: Manifests M, A, F, F2; the PU materials at Burt's corrected 32D R4 100; the stored 4G factor 5 581 / 4 100. The header reads `v1.59.2` |
| Deploy to | **the merge commit of the release PR**. #207 (`60f5d56`, 2 Oct 07:36 SAST) and #209 (`caf6966`, 09:00 SAST: #208's identical tree — #208 itself merged into its stacked branch, not the base) are on the base; then the release PR. The annotated tag **`v1.59.3`** goes on the release PR's merge commit **before** the deploy; `mkstage.sh` records both in `expected.env` |
| Range | `1d9cb47..<target>`: #206 (the RT1 close: OUTCOME, CI snapshot = prod 1 Oct 13:11, prune #5, the F entry), #207 (Part 1 + 1c: a quote never writes the Body Template; the per-body default foam), #209 = #208 (Part 2: the golden on Burt's 21 Sep set + 2 proven corrections, pinned packs, the prod list), the release PR (Manifest P, G1, the 15-body CI snapshot, this runbook, the kits, `backend/VERSION`) |
| DB migration | **0050** `0050_trailer_default_insulation_foam.py`: `trailer_types.default_insulation_foam` VARCHAR(8) NOT NULL DEFAULT `'32D'` + CHECK `IN ('32D','4G')`. Additive, inspector-guarded, no backfill: every body reads `32D` after it. **The kit takes a full `pg_dump` before it** (step 4, RT2_RULING_1 R6.1); `icb-deploy.sh` also runs its own `icb-pg-backup` |
| Frontend rebuild | **none** — `frontend/` untouched (asserted); the SPA bundle must stay byte-identical |
| Service restart | **YES** — `app/database.py`, `app/routers/trailers.py` (+ `tools/costing_audit/*`, which the audit page imports in-process) |
| Templates + static | `calculator.html` (`?v=184` → **`185`**), `calculator2.html` (`?v=126` → **`127`**), `admin_templates.html` (`?v=18` → **`19`**) and their three scripts: they reload from disk |
| Dependencies | **none** (`requirements` unchanged, asserted). PyYAML 6.0.2 is in the venv since v1.59.0 (asserted) |
| Env / `.env` | none |
| Data | **Manifest P** (Part 3, ratified): every active own-priced PU foam line onto the shared PU price — P1 own-price removals, P2 conversions to Burt's row shape (formula + own price, one transaction). **PENDING R8: N entries on L lines** (provisional on the 1 Oct 13:11 data: 47 entries on 33 lines; with the 15-body export 59 on 39). The 18 chiller PU lines stay as they are (no PU on chillers, Burt 1 Oct). **Manifest D** (R6): the four 4G body defaults, `32D` → `4G` on MEAT HANGER LARGE (12), MEAT HANGER SMALL-MEDIUM (36), EXPLOSIVE 4.9 AND UP (24), RHINORANGE TRAILER (15). **D strictly after P** (asserted) |
| Window extra | The door test (Michael toggles a test quote DRD ↔ SRD and EPS ↔ PU several times) → the door report must still read **14 OK**: the prod proof of Part 1 |

## Why

- **A quote never changes a Body Template** (#207, RT2 Part 1). Opening, rendering and editing a quote wrote the
  template's rear-door thickness: two writes fired on open/render from the browser's remembered state, without a
  click (RT2_RETURN_1 §1.2). That is RT1's door-report timeline (12 → 11 → 10 → 12 → 13 → 14 OK). Now:
  - the door and thickness changes a quote makes stay in that quote. They are saved in its `body_variables` and
    restored on re-open (R3);
  - a `PUT /api/bom/{id}` that carries only a thickness is admin-only, and refuses with *"Template thickness is set
    in Body Templates by an administrator."* (R2);
  - the TEMPLATE UPDATED warning is gone.
- **A per-body default foam** (#207, Part 1c, R6). Four bodies are 4G on Burt's sheets. Each now opens on
  `4G (body default)`, set by an administrator in Body Templates. The browser's remembered foam no longer decides a
  new quote's grade; a saved costing keeps its own.
- **The audit refresh** (#208, Part 2). The golden is rebuilt on Burt's sealed 21 Sep set plus two documented
  corrections, each proven move-only:
  - PU!C17 4 095 → 4 100;
  - SUB FRAME + LIGHT BOX ASSY GALV PLATE onto the 1.0 MM price.

  The packs are pinned, and the prod list is re-judged.
- **One shared PU price** (#208 + Manifest P, Part 3). No PU foam line carries its own price, and every line works
  out its own volume. G1 guards it in CI.

## The kits (committed with this runbook, staged byte-exact)

| kit | runs | what |
|---|---|---|
| `ops/prod-release-v1.59.3/release.sh` | `preflight` · `verify` · `deploy` | the code release: v1.59.2's kit + v1.59.0's migration handling (backup, the 0050 chain, the dry-run's `DB migration YES - 0050_…`) + three cache-busted bundles |
| `ops/prod-release-v1.59.3/mkstage.sh` | CA, Git Bash | stages it from committed blobs; derives every expected value from the trees (the migration chain 0049 → 0050, each bundle's `?v=` and blob before/after); **refuses to stage until the annotated tag is on origin** and peels to the target |
| `ops/prod-rt2/rt2_data.sh` | `dryrun P\|D` · `apply P\|D` · `revert <journal>` | Manifest P through `backend/tools/audit_pricing_corrections.py --target prod`; Manifest D through `ops/prod-rt2/rt2_defaults.py --target prod`. Both only over v1.59.3 / alembic 0050; **D only after P is fully on; P's revert only after D's** |
| `ops/prod-rt2/mkstage_data.sh` | CA, Git Bash | stages both tools + the manifest; the plan sizes (`P_TODO`, `D_TODO = 4`) and shas go into `expected.env` |
| `ops/prod-rt2/rt2_all.sh` (+ `rt2_all_compare.py`, `mkstage_all.sh`) | `pre` · `post` · `afterP` · `afterD` · `close` — read only | the audit **All** from the CLI (the deployed code's golden, packs and prod list), then the page's newest All against it **cell by cell**: `PAGE_EQUALS_CLI` |
| `ops/prod-rt2/rt2_doors.sh` (+ RT1's `rt1_door_report.py`, unchanged) | read only | the rear-door thickness report (the door test, and the close) |
| `ops/prod-rt2/rt2_export.sh` (+ `mkstage_export.sh`) | read only | the R8 export of the 15 bodies — **before** the window (RT2_RULING_1 R8) |

**Named STOPs, code:** `KIT`, `DB`, `GIT`, `ANCHORS`, `PYYAML`, `BACKUP`, `GUARD`, `TAG`, `DRYRUN`, `DEPLOY`, `RESTART`,
`RECORD`, `BYTES_BEFORE`, `BYTES_AFTER`, and each check by name: `HEAD`, `TAG_LOCAL`, `DESCRIBE`, `ALEMBIC`, `COLUMN`,
`CHECK_CONSTRAINT`, `ACTIVE`, `RESTART_AFTER_CODE`, `WORKERS`, `BOOTSTRAP_FAILED`, `TRACEBACKS`, `HEALTH`, `PYYAML`,
`TOOL_IMPORT`, `OPENAPI_DOORS_EQUAL`, `V_<bundle>`, `LOCAL_<bundle>`, `LAN_<bundle>` (calculator, calculator2,
admin_templates), `SPA_LOCAL`, `SPA_LAN`, `DEFAULTS_ALL_32D`. **Data:** `KIT`, `DB` (alembic must be 0050), `CODE` (only over
v1.59.3), `IMPORT`, `ORDER` (D needs P fully on; P's revert needs D off), `GUARD`, `OTHERS` (another body already 4G),
`PLAN`, `BACKUP`, `APPLY`, `JOURNAL`, `AFTER`, `REVERT`. **All:** `KIT`, `DB`, `CODE`, `RUN` (a pack crashed or wrote no
report), `PAGE` (no finished page run in the last 45 min). Decorative pipelines carry `|| true`; there is no bare `set -e`.

**The Python proof.** This range adds no route and changes no schema: `app.openapi()` built from `1d9cb47` and from
the release tree is byte-identical (378 paths, sha256 `45781eb4…`), so `/openapi.json` proves only that the two doors
agree. The kit proves the new Python from the process side:
- `RESTART_AFTER_CODE`: the service started after the fast-forward (icb's reflog against the service's monotonic
  start);
- the MainPID changed;
- exactly 4 workers logged startup after the restart;
- **0050's column and CHECK exist**, and only the new code's migration writes them.

The user-visible proof is Michael's, signed in:
- the header reads `v1.59.3`;
- Body Templates shows the **Default foam** select;
- after D, MEAT HANGER LARGE opens on **`4G (body default)`**, which only the new Python's `/api/trailers` field
  produces.

## Sequence

**0. Michael picks the window.** About 45–60 min in one sitting. The restart is a few seconds of outage on all four
workers; the migration adds one column to a 40-row table (instant). Nadie's and Lezette's quoting hours are the
constraint. Nothing changes on prod before the window except the R8 export (read only).

**1. Merge, tag, stage (before the window, after RT2_RULING_2).**
- #207 and #209 are merged (CI green on each exact head). CI green on the release PR's exact head → Michael's merge
  word → merge it. **Retarget a stacked PR to `backport/v1.39-base` before merging it** (#208 merged into its parent
  branch). The release PR's merge commit is the target; its tree must equal the CI-tested tree.
- The CA tags it: `git tag -a v1.59.3 <merge-sha> -m "…"`, `git push origin v1.59.3`, and proves the **tag object** on
  origin equals the local one (`git ls-remote --tags origin v1.59.3`), peeled = the merge commit.
- The CA stages the kits from the merge commit:
  - `bash ops/prod-release-v1.59.3/mkstage.sh <out> <merge-sha>`
  - `bash ops/prod-rt2/mkstage_data.sh <out> <merge-sha>`
  - `bash ops/prod-rt2/mkstage_all.sh <out> <merge-sha>` (after the tag: it then covers v1.59.2 **and** v1.59.3)
- Michael copies them (the CA's own writes to the VM are refused, correctly). From Windows PowerShell:
  - `scp "<out>\icb-release-v1.59.3.tar" "<out>\icb-rt2-data.tar" "<out>\icb-rt2-all.tar" "<out>\icb-rt2-doors.tar" mickeyger@192.168.0.251:/tmp/`
  - `ssh mickeyger@192.168.0.251 "cd /tmp && tar -xf icb-release-v1.59.3.tar && tar -xf icb-rt2-data.tar && tar -xf icb-rt2-all.tar && tar -xf icb-rt2-doors.tar"`

**2. Preflight + the known-hit check (read only, any time before the window).** On the VM:

```
sudo bash /tmp/icb-release-v1.59.3/release.sh preflight
sudo bash /tmp/icb-release-v1.59.3/release.sh verify
```

(From Windows: `ssh -t mickeyger@192.168.0.251 "sudo bash /tmp/icb-release-v1.59.3/release.sh preflight"`; `-t` lets
sudo prompt; do not pipe it.)

- `preflight` asserts:
  - db `icb_platform`, alembic 0049, HEAD `1d9cb47`, no tracked modifications;
  - **the 0050 column is absent**;
  - each of the three pages loads its v1.59.2 `?v=`, and both doors serve the v1.59.2 blob under it;
  - the SPA served = disk on both doors;
  - health 200; PyYAML 6.0.2;
  - **the `v1.59.3` tag object is on origin**;
  - the backup directory is writable;
  - `deploy/prod/icb-deploy.sh` is the expected blob, and icb's sudo is NOPASSWD.
- `verify` before the deploy **must fail on exactly 15 checks** and pass the other 11:
  - the 15 are `HEAD`, `TAG_LOCAL`, `DESCRIBE` (`v1.59.2` today), `ALEMBIC` (0049), `COLUMN`, `CHECK_CONSTRAINT`, and
    for each of the three bundles `V_`, `LOCAL_` and `LAN_` (the old `?v=` and blob);
  - that proves each check can see what it is meant to see;
  - `TRACEBACKS` counts since the current service start (30 Sep 20:51). If prod has logged an error since, it fails
    too and prints the excerpt. That is pre-existing: report it, it does not block.

**3. The window.**

| # | who | step | pass condition |
|---|---|---|---|
| 1 | Michael | Admin → Costing audit → **All**; when it has finished, `sudo bash /tmp/icb-rt2-all/rt2_all.sh pre` | `PAGE = CLI`; the counts = **table 1** (prod's v1.59.2 golden + list, as today) |
| 2 | Michael | `sudo bash /tmp/icb-release-v1.59.3/release.sh deploy` | `######## DEPLOYED`: every step below; `DEFAULTS_ALL_32D` = 0 |
| 2+ | CA | the Cloudflare door, from outside, **only now** (a CF probe before the disk matched would cache old bytes under the new URL) | `mes.icecoldgrp.online`: the three bundles at their new `?v=` = the target blobs; `/openapi.json` = the LAN door |
| 3 | Michael | **All** → `rt2_all.sh post` | `PAGE = CLI` at the same moment; the counts = **table 2** (the new golden, packs and list on prod's data: **"No change" is not the test**) |
| 4 | Michael | `sudo bash /tmp/icb-rt2-data/rt2_data.sh dryrun P` → `… apply P` | dry-run **N to apply, 0 already applied**, 0 mismatches → applied, journal kept → second dry-run **0 to apply, N already applied** |
| 5 | Michael | **All** → `rt2_all.sh afterP` | `PAGE = CLI`; the counts = **table 3**: against step 3, **only P's cells move** (the list below) |
| 5b | Michael | `rt2_data.sh dryrun D` → `… apply D` | the order check reads P fully on; dry-run **4 to apply, 0 already applied**, `OTHERS_4G: 0` → applied → **0 to apply, 4 already applied** |
| 5c | Michael | **All** → `rt2_all.sh afterD` | `PAGE = CLI`; the counts = **table 4**: against step 5, **only EXPLOSIVE 4.9 AND UP's default-foam cells move** (the probe now opens it on 4G, R6.4) |
| 6 | Michael | **the door test**: a test quote (not saved) on any of the 14 bodies — toggle DRD ↔ SRD and EPS ↔ PU several times, edit a door thickness, close — then `sudo bash /tmp/icb-rt2-doors/rt2_doors.sh` | **SUMMARY: 14 OK**, every body's "then → now" unchanged: the toggles wrote nothing to the Body Templates |
| 7 | Michael | the click-through (below) | all seen |

D's own All (5c) is a CA proposal for RULING_2. D moves pack cells of its own: the explosive pack's EXPLOSIVE 4.9
golden is 4G (`foam_default: 4G`), and before D the probe opens that body on 32D. One All after P and one after D
attribute every moved cell to one change. Without 5c, step 5 runs after 5b and table 3 + table 4's movement is
checked together.

`release.sh deploy`, step by step:

| step | what | asserted |
|---|---|---|
| 1 anchors | the start state | HEAD `1d9cb47` + alembic 0049 (fresh); or HEAD = target with alembic 0049 or 0050 (resume: a migration or restart that failed part way); or HEAD = target + 0050 + the completion record (already deployed: asserts only). No tracked modifications; rollback anchor written |
| 2 bytes before | the served baseline | each page loads its v1.59.2 `?v=` (184 / 126 / 18); both doors serve the v1.59.2 blobs; SPA served = disk |
| 3 PyYAML | present | `import yaml` = 6.0.2 (nothing is installed) |
| 4 **backup** | `pg_dump -Fc icb_platform` → `/var/backups/postgres/icb_platform_pre-v1.59.3_<ts>.dump` (mode 600) | exists, size > 0, sha256 printed; `pg_restore --list` has TABLE DATA incl. `alembic_version`, `trailer_types` and `bill_of_materials`. **The rollback for 0050, and the window's restore point before the code, the schema and the data move** |
| 5 fetch + guards | `git fetch origin --tags` as icb | `origin/backport/v1.39-base` = the staged target; **`refs/tags/v1.59.3` = the staged tag object, peels to the target, `git describe` at the target = `v1.59.3`**; `1d9cb47` is an ancestor; the changed-file count **and** C-sorted sha256 equal the staged values; **exactly one new migration = `0050_trailer_default_insulation_foam.py`**; no `requirements` change; `frontend/` and `deploy/` untouched |
| 6 dry run | `deploy/prod/icb-deploy.sh <target> --dry-run` as icb (the expected blob) | plan = "DB migration YES - 0050_trailer_default_insulation_foam.py", "SPA rebuild no", "Service restart YES" |
| 7 deploy | `icb-deploy.sh <target> --yes` as icb: its own backup, ff-only, **alembic upgrade head**, restart, health | exit 0 and "DEPLOYED"; MainPID changed; `/var/tmp/icb-deploy-state` = `completed <target>` |
| 8 post-deploy | after 20 s | HEAD = target; `v1.59.3` local = the staged object; `git describe` = `v1.59.3`; **alembic 0050; the column = `character varying\|8\|NO\|'32D'::character varying`; the CHECK present; every body `32D`**; active; **the service started after the code moved**; **exactly 4** "Application startup complete" since the restart; **0** BOOTSTRAP FAILED; **0** tracebacks; health 200; PyYAML; the audit + correction tools import; `/openapi.json` local = LAN; **each page loads its new `?v=` (185 / 127 / 19), exactly one tag each, and both doors serve the target blob under it**; the SPA unchanged |

Everything is logged under `/tmp/icb-release-v1.59.3/out-<mode>-<ts>/`, `/tmp/icb-rt2-data/out-<mode>-<X>-<ts>/`,
`/tmp/icb-rt2-all/out-<label>-<ts>/` and `/tmp/icb-rt2-doors/out-<ts>/` (`run.log`, the dry-runs, the journals, the
reports, `OUTCOME.txt`). The CA fetches them.

**The click-through (7), on the domain, signed in:**

| check | expected |
|---|---|
| the page header | **v1.59.3** (also `/debug/health` → `"version": "v1.59.3"`) |
| Body Templates → MEAT HANGER LARGE (and the other three 4G bodies) | the **Default foam** select reads **4G**; any other body reads **32D** |
| Calculator → a **new** costing on MEAT HANGER LARGE, default size (6.7 × 2.6 × 2.6), PU panels, double door | the foam selector reads **`4G (body default)`** — whatever this browser chose last time; the PU panels total **PENDING R8** (= Burt's MEAT BODY at 4G, apart from the named single-rear-door gap R6.6, +≈R530 on a single door only) |
| … switch to 32D, then open a new costing on the same body | the new costing opens on **4G (body default)** again (the browser's memory no longer decides) |
| … a saved 32D MEAT HANGER costing, re-opened | it re-opens on **32D**, its own grade |
| … toggle double ↔ single door, EPS ↔ PU, edit a door thickness | the toast says **"this quote only"**; no TEMPLATE UPDATED warning; the door report afterwards: 14 OK (step 6) |
| EXPLOSIVE UP TO 2.7, default size, PU, double door | **bom 5210 (DRD PU) prices R999.73** (Burt's), not R1 463 (R7: 5284 = 0.041) |
| one converted explosive line (EXPLOSIVE 4.9 AND UP, a P2 line — PENDING R8 which) | equals Burt's row at the default size and the body's default foam |
| FREEZER MEDIUM → **single door** | REAR FRAME & FLOOR PLATE reads **NOT SELECTED** (v1.59.2, unchanged) |
| a 32D body (e.g. FREEZER LARGE), a new costing | opens on **32D** — unchanged |

## Expected audit movement — PENDING R8 (the mirror rehearsal on the R8 export)

Table 1 (step 1, v1.59.2's golden + its list, prod's data with R7), table 2 (step 3), table 3 (after P), table 4
(after D), each with per-pack UNVERIFIABLE / ACCEPTED / PASS / SKIP / FLAG and the exact moved-cell lists between
steps, come from the mirror loaded from the R8 export:
- step 1 runs v1.59.2's own CLI;
- steps 3 to 5c run the release tree's CLI;
- each step is checked page against CLI with `rt2_all_compare.py`, as on prod.

The mirror's page-against-CLI test on the 1 Oct 13:11 data already reads 2 702 of 2 702 cells identical (with a
one-cell negative control).

## Rollback (decided before the run; the code and the data rollbacks are independent)

- **Code:** back to `1d9cb47` and restart:
  `sudo -u icb bash /opt/icb-platform/deploy/prod/icb-rollback.sh 1d9cb47`, or directly
  `sudo -u icb git -C /opt/icb-platform reset --hard 1d9cb47` then `sudo systemctl restart icb-backend`.
  - Re-probe the three doors.
  - No SPA rebuild (frontend untouched).
  - **0050 stays** (additive; `icb-deploy.sh` never downgrades). The v1.59.2 code does not read the column, and a body
    it creates gets the server default `32D`.
  - D is inert under v1.59.2; P is correct under it (the shared price, 4G when 4G is selected).
  - The tag stays. After the restart the header reads `v1.59.2` again (`git describe` at `1d9cb47`).
- **Data:** `sudo bash /tmp/icb-rt2-data/rt2_data.sh revert /var/backups/icb-rt2-2026-10/journal_<P|D>_<…>.json`.
  - **D first, then P** (asserted: P's revert refuses while D is on).
  - D's revert puts the four rows back to `32D` byte for byte, and refuses if a body was renamed since.
  - P's revert puts every journaled line back column for column and deletes the `bom_override_history` rows the
    apply wrote. It refuses if a line moved since.
  - P is proved byte-exact on the prod mirror (PENDING R8), and D in `backend/tests/test_rt2_manifest_d_defaults.py`.
- **Last resort:** the step-4 dump `icb_platform_pre-v1.59.3_<ts>.dump` (the whole database before the window).

**After a STOP:**
- **Code, before step 7:** nothing on prod has changed (a backup file may exist).
- **Code, from step 7 on:** re-running `release.sh deploy` resumes. At the target without a completion record,
  `icb-deploy.sh` re-runs its idempotent steps: `alembic upgrade head` (it runs 0050 if it had not, otherwise a no-op)
  and the restart. Every assert runs again (simulated: a failed migration and a failed restart both resume to
  DEPLOYED).
- **Data:** a dry-run or apply STOP writes nothing (one transaction, guards before any write). An `AFTER` STOP means
  the apply committed but the second dry-run still found work: tell the CA before anything else.
- **All:** `the page and the CLI DIFFER` changes nothing. Stop and tell the CA.
- **`BOOTSTRAP FAILED`** is the known worker race; one more restart normally heals it.

## Simulation (WSL, 2 Oct; the real `icb-deploy.sh`, the real `mkstage*.sh`)

**Code kit** (`ops/prod-release-v1.59.3/sim/run_sim.sh`). The fake prod is at `1d9cb47` with the `v1.59.2` tag but
without `v1.59.3`, and a fake database starts at alembic 0049. The sim origin is `origin/backport/v1.39-base` plus the
RT2 code and the kit, with a real annotated `v1.59.3`; the kit is staged by the real `mkstage.sh`. The REAL
`icb-deploy.sh` runs, its migration step included; the alembic stub moves 0049 → 0050.

| scenario | result |
|---|---|
| happy | preflight PASS → `verify` fails on exactly the 15 and passes 11 → deploy **DEPLOYED** (the kit's backup taken at alembic 0049, before the migration; `icb-pg-backup` ran once; 0049 → 0050; column + CHECK; 4 workers; the service started after the code moved; the three bundles at 185 / 127 / 19 on both doors) → `verify` 0 failures → deploy again = **ALREADY DEPLOYED**. No root-owned `__pycache__` left in the repo |
| tag not on origin | preflight fails `TAG_ON_ORIGIN` only → deploy **STOP [TAG]** after the fetch |
| prod moved by hand | **STOP [ANCHORS]** |
| a worker logs BOOTSTRAP FAILED | `icb-deploy.sh` fails → **STOP [DEPLOY]** naming the anchor and the backup |
| a traceback after the restart | **STOP [TRACEBACKS]**; a re-run stops on it too |
| the doors serve old calculator bytes after the restart | **STOP [LOCAL_calculator]** |
| the restart fails after the migration | **STOP [DEPLOY]** → re-run = **RESUME** (alembic 0050) → DEPLOYED → `verify` 0 → ALREADY DEPLOYED |
| **the migration fails** | **STOP [DEPLOY]** (code at the target, alembic still 0049) → re-run = **RESUME** (alembic 0049 accepted) → the migration runs → DEPLOYED → `verify` 0 → ALREADY DEPLOYED |
| the backup has no `trailer_types` data | **STOP [BACKUP]**, before the fetch: nothing moved |

**Data kit** (`ops/prod-rt2/sim/run_data_sim.sh`: the real `rt2_data.sh` + `mkstage_data.sh` over stand-ins for both
tools that keep their output contracts; the provisional Manifest P of 47 entries) — **21 of 21**:
- **the window order:** dry-run / apply D before P → **STOP [ORDER]**; dry-run P = 47 to apply; apply P (pre-apply
  backup, journal, provenance in `/var/backups/icb-rt2-2026-10/`, second dry-run clean); apply P again → already
  applied; dry-run D = 4 to apply; apply D; apply D again → already applied;
- **the reverts:** revert P while D is on → **STOP [ORDER]**; revert D; revert P; revert P again → **STOP [REVERT]**;
  dry-run D after P is reverted → **STOP [ORDER]**;
- **the guards:** another body already 4G → **STOP [OTHERS]**; a P guard mismatch → **STOP [GUARD]** (and D's order
  check refuses); a P plan of the wrong size → **STOP [PLAN]**; alembic 0049 (before the deploy) → **STOP [DB]**; a
  tampered manifest → **STOP [KIT]**; prod's code moved → **STOP [CODE]**.

**The D tool itself** (`backend/tests/test_rt2_manifest_d_defaults.py`, a real Postgres, 8 tests):
- the dry-run plans the four and writes nothing;
- **P first:** an own-priced PU foam line on any of the four refuses the dry-run and the apply (exit 2, no journal);
- apply → the four rows, one transaction, a journal; a second apply is a no-op;
- revert is byte-exact and idempotent;
- a partly applied set applies only the rest;
- a renamed body refuses the whole apply, and the revert;
- the database pin;
- the committed bodies = R6's four.

Negative control: with the P-first guard disabled, exactly the P-first test fails.

**All + doors** (`ops/prod-rt2/sim/run_all_sim.sh`) — **14 of 14**:
- `pre` over v1.59.2 = PAGE = CLI, and the five packs run from the deployed backend;
- a page / CLI difference is reported ("change nothing"); no page run → **STOP [PAGE]**;
- unaccepted cells are reported, not a stop; a crashing pack → **STOP [RUN]**;
- staged before the tag, it refuses v1.59.3 (**STOP [DB]**); re-staged after the tag, `post` passes over v1.59.3;
- the door report runs over both codes;
- code moved / tampered kit → **STOP [CODE]** / **[KIT]**.

The real compare on the prod mirror reads 2 702 / 2 702 cells identical between the page's own run path and the CLI.
Nudging one CLI cell by R1 gives `PAGE_EQUALS_CLI: no (2701 of 2702)`, exit 1.

The simulations found one kit defect before any prod use, now fixed. Two runs in the same second shared an output
folder, so a crashed pack could hide behind the previous run's report. Every kit now refuses an existing output
folder, and the All kit stops on any pack exit other than 0 / 1.

## After the window (RT2 Stage 4, the close)

- **Snapshot = prod** with the CI guard green: the read-only export again after P and D; G1's PENDING-P allowance comes
  out with it.
- **Re-judge entry #12** after P (R6.4; on the mirror it is down to 24 plywood cells, not 0: PENDING R8 / BA).
- The door report **14 OK** at close; the OUTCOME; the docs PR; **Michael removes the `/tmp` staging on the VM.**

## OUTCOME

(after the window)
