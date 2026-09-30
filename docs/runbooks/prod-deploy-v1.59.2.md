# Prod deploy: v1.59.2 (RT1 release train) — the code release, then Manifests A and B, in one window

Target: **`https://192.168.0.251/mes-app/`** and **`https://mes.icecoldgrp.online`** · repo `/opt/icb-platform`
· service `icb-backend` (`uvicorn --workers 4`) · DB `icb_platform` · BA dispatch **RT1** (release ops, one CA).

| | |
|---|---|
| Prod is at | **v1.59.0 `de74796`** (28 Sep 15:28 SAST), alembic **0049**, `calculator.js?v=182`. The header reads `v1.50.0`: prod's repo has never fetched the `v1.59.0` tag |
| Deploy to | **the squash-merge commit of the release PR #204.** The annotated tag **`v1.59.2`** goes on that commit **before** the deploy (RT1 ruling 2); `mkstage.sh` records both in `expected.env` |
| Range | `de74796..<target>`: #199 (v1.59.0 OUTCOME), #201 (CI flakes + repair category `ORDER BY`), #200 (NOT SELECTED header, the Designer keeps rules), #202 (the correction tool learns `bom_conditions`, Manifest A), #203 (rule chips from the database, plain-English exclusions), #204 (this runbook, the kits, `backend/VERSION`) |
| DB migration | **none** — asserted by the kit (no new file under `backend/alembic/versions/`); alembic stays 0049 |
| Frontend rebuild | **none** — `frontend/` untouched (asserted); the SPA bundle must stay byte-identical |
| Service restart | **YES** — 5 app `.py` files: `formula_engine.py`, `routers/calculator.py`, `routers/repair_templates.py`, `routers/trailers.py`, `services/free_hand.py` |
| Templates + static | `calculator.html` (`calculator.js?v=182` → **`?v=184`**), `calculator.js`, `admin_configurator_preview.html`, `admin_visual_configurator_settings.html`: they reload from disk |
| Dependencies | **none** (`requirements` unchanged, asserted). PyYAML 6.0.2 is already in the venv since v1.59.0 (asserted, nothing installed) |
| Env / `.env` | none |
| Data, after the code is accepted | **Manifest A**: 120 REAR FRAME & FLOOR PLATE inclusion rules on 14 bodies. **Manifest B**: the MEAT HANGER single-door PU lines + own R4 100 prices (built from prod as it is now). Each is its own paste with its own dry-run and journal, **in the order code → A → B** |

## Why

Tested changes were not reaching prod, and prod is where Michael fixes costings for the sales team (RT1 dispatch).
This window ends with prod carrying every tested change, verified, and the audit page as Michael's working tool:

- **NOT SELECTED** (#200): a section whose every line is out by a rule shows a `NOT SELECTED` header instead of
  vanishing; the eye shows its struck-through lines.
- **The Trailer Designer keeps rules it cannot show** (#200): the rule editor no longer *replaces* a rule whose
  conditions sit outside the category's branch (it silently became `FRONT EPS = N` before). This is what makes
  Manifest A's rules safe to edit on prod.
- **Rule chips from the database; plain English on struck lines** (#203): the Designer's chips read the stored rule;
  a rule-excluded calculator line reads e.g. `not used with SRD PU`.
- **Repair category line order** (#201): `ORDER BY sort_order, id` (a journey flake, and a real order).
- **Data:** a single rear door (SRD) quote no longer costs REAR FRAME & FLOOR PLATE (Michael's ruling, 28 Sep,
  closes accepted entry #5), and the MEAT HANGER single-door PU line stops pricing ≈ R24.4k.

## The kits (committed with this runbook, staged byte-exact)

| kit | runs | what |
|---|---|---|
| `ops/prod-release-v1.59.2/release.sh` | `preflight` · `verify` · `deploy` | the code release (from the proven v1.59.0 kit) |
| `ops/prod-release-v1.59.2/mkstage.sh` | CA, Git Bash | stages it from committed blobs; derives every expected value from the target tree; **refuses to stage until the annotated tag is on origin** and peels to the target |
| `ops/prod-rt1/rt1_data.sh` | `dryrun A\|B` · `apply A\|B` · `revert <journal>` | Manifests A and B through `backend/tools/audit_pricing_corrections.py --target prod` |
| `ops/prod-rt1/mkstage_data.sh` | CA, Git Bash | stages the tool + both manifests; the plan sizes (`A_TODO`, `B_TODO`) and manifest shas go into `expected.env` |
| `ops/prod-rt1/rt1_snapshot.sh` (+ `rt1_door_report.py`, `mkstage_snapshot.sh`) | read only | the prod snapshot + reference run + rear-door thickness report (RT1 1b, and the Stage 3 baseline) |

**Named STOPs, code:** `KIT`, `DB`, `GIT`, `ANCHORS`, `BYTES_BEFORE`, `PYYAML`, `BACKUP`, `GUARD`, `TAG`, `DRYRUN`, `DEPLOY`,
`RESTART`, `RECORD`, `TRACEBACKS`, `BYTES_AFTER`, and each post-check by name (`HEAD`, `TAG_LOCAL`, `DESCRIBE`, `ALEMBIC`,
`ACTIVE`, `RESTART_AFTER_CODE`, `WORKERS`, `BOOTSTRAP_FAILED`, `HEALTH`, `PYYAML`, `TOOL_IMPORT`, `OPENAPI_DOORS_EQUAL`,
`TEMPLATE_V`, `CALC_LOCAL`, `CALC_LAN`, `SPA_LOCAL`, `SPA_LAN`). **Data:** `KIT`, `DB`, `CODE` (the data goes on only
over the v1.59.2 code), `IMPORT`, `ORDER` (B needs A on prod; A's revert needs B reverted), `GUARD` (any mismatch: prod
moved, nothing written), `PLAN` (the plan is not the reviewed size), `BACKUP`, `APPLY`, `JOURNAL`, `AFTER`, `REVERT`.
Decorative pipelines carry `|| true`; there is no bare `set -e`.

**Why the kit cannot use `/openapi.json` as the Python proof this time.** v1.59.0 added 6 routes; this range adds none.
`app.openapi()` built from `de74796` and from `22b9d20` is byte-identical (378 paths). So the kit proves the new Python
is running from the process side: the fast-forward precedes the service start (`RESTART_AFTER_CODE`, from icb's reflog
and the service's monotonic start), the MainPID changed, and exactly 4 workers logged startup after it. The
user-visible proof is Michael's, signed in (step 2g): the header reads `v1.59.2`, and the NOT SELECTED header and the
`not used with SRD PU` reason exist only in the new Python.

**Proved before use in a WSL simulation** (the v1.59.0 method): prod's paths bind-mounted from a scratch folder in a
private mount namespace; the **real `deploy/prod/icb-deploy.sh`** runs; systemd, postgres, curl, sudo, npm and the venv
are stubs; the fake prod is at `de74796` **without** the `v1.59.0` tag (as the VM: its header reads v1.50.0), the sim
origin carries the release branch and a real annotated `v1.59.2`, and the kit is staged by the real `mkstage.sh`.
Results: see *Simulation* below.

## Sequence

**0. Michael picks the window.** About 30–45 min in one sitting. The restart is a few seconds of outage on all four
workers; Nadie's and Lezette's quoting hours are the constraint. Nothing changes on prod before the window.

**1. Merge, tag, stage (before the window).**
- CI green on #204's exact head → Michael's merge word → squash-merge. The merge commit's tree must equal the
  CI-tested tree (CI runs on the PR only, never on a push to this branch).
- The CA tags it: `git tag -a v1.59.2 <merge-sha> -m "…"`, `git push origin v1.59.2`, and proves the **tag object** on
  origin equals the local one byte for byte (`git ls-remote --tags origin v1.59.2`), peeled = the merge commit.
- The CA stages both kits from the merge commit:
  `bash ops/prod-release-v1.59.2/mkstage.sh <out> <merge-sha>` and `bash ops/prod-rt1/mkstage_data.sh <out> <merge-sha>`.
- Michael copies them (the CA's own writes to the VM are refused, correctly). From Windows PowerShell:
  - `scp "<out>\icb-release-v1.59.2.tar" "<out>\icb-rt1-data.tar" mickeyger@192.168.0.251:/tmp/`
  - `ssh mickeyger@192.168.0.251 "cd /tmp && tar -xf icb-release-v1.59.2.tar && tar -xf icb-rt1-data.tar"`

**2. Preflight + the known-hit check (read only, any time before the window).** On the VM:

```
sudo bash /tmp/icb-release-v1.59.2/release.sh preflight
sudo bash /tmp/icb-release-v1.59.2/release.sh verify
```

(From Windows: `ssh -t mickeyger@192.168.0.251 "sudo bash /tmp/icb-release-v1.59.2/release.sh preflight"`; `-t` lets
sudo prompt; do not pipe it.)

- `preflight` asserts: db `icb_platform`, alembic 0049, HEAD `de74796`, no tracked modifications; the calculator page
  loads `?v=182` and both doors serve the v1.59.0 `calculator.js` blob; the SPA served = disk on both doors; health 200;
  PyYAML 6.0.2; **the `v1.59.2` tag object is on origin**; the backup directory is writable; `deploy/prod/icb-deploy.sh`
  is the expected blob; icb's sudo is NOPASSWD.
- `verify` before the deploy **must fail on exactly 6 checks** — `HEAD`, `TAG_LOCAL` (the tag arrives with the deploy's
  fetch), `DESCRIBE` (`v1.50.0` today), `TEMPLATE_V` (182), `CALC_LOCAL`, `CALC_LAN` (the old blob) — and pass the other
  12. That proves each check can see what it is meant to see. (`TRACEBACKS` counts since the current service start,
  28 Sep 15:28: if prod has logged an error since, it fails too and prints the excerpt. That is pre-existing, and worth
  knowing before a deploy: report it, it does not block.)

**3. The window.**

| # | who | step | pass condition |
|---|---|---|---|
| 2a | Michael | Admin → Costing audit → **All** | the pre-deploy reference run |
| 2b | Michael | `sudo bash /tmp/icb-release-v1.59.2/release.sh deploy` | `######## DEPLOYED`: every step below |
| 2b | CA | the third door, from outside, **only now** (a CF probe before the disk matched would cache old bytes under the new URL) | `mes.icecoldgrp.online`: `calculator.js?v=184` and `/openapi.json` byte-identical to the LAN door |
| 2c | Michael | **All** again | **"No change since" 2a.** Any changed cell = STOP: report it, change nothing |
| 2d | Michael | `sudo bash /tmp/icb-rt1-data/rt1_data.sh dryrun A` → `… apply A` | dry-run **120 to apply, 0 already applied**, 0 mismatches → applied, journal kept → second dry-run finds nothing |
| 2e | Michael | `… dryrun B` → `… apply B` (only if RT1_RULING_1 keeps a Manifest B) | dry-run **`B_TODO` to apply** (the ruled plan, pinned in `expected.env`) → applied → second dry-run finds nothing |
| 2f | Michael | **All** | the 57 SRD REAR FRAME cells went **ACCEPTED → SKIP** (both sides R0); nothing else moved except B's 12 cells (+R1.78, default B only) — the counts in *Expected audit movement* |
| 2g | Michael | the click-through (below) | all seen, and **every body ends on the door it opened with** |

`release.sh deploy`, step by step:

| step | what | asserted |
|---|---|---|
| 1 anchors | the start state | HEAD `de74796` + alembic 0049 (fresh), or HEAD = target (resume / already deployed); no tracked modifications; rollback anchor written |
| 2 bytes before | the served baseline | the calculator page loads `?v=182`; both doors serve the v1.59.0 blob; SPA served = disk |
| 3 PyYAML | present | `import yaml` = 6.0.2 (nothing is installed) |
| 4 **backup** | `pg_dump -Fc icb_platform` → `/var/backups/postgres/icb_platform_pre-v1.59.2_<ts>.dump` (mode 600) | exists, size > 0, sha256 printed, `pg_restore --list` has TABLE DATA incl. `bill_of_materials`. **No migration runs; this is the window's restore point before the code and the data move** |
| 5 fetch + guards | `git fetch origin --tags` as icb | `origin/backport/v1.39-base` = the staged target; **`refs/tags/v1.59.2` = the staged tag object, peels to the target, `git describe` at the target = `v1.59.2`**; `de74796` is an ancestor; the changed-file count **and** C-sorted sha256 equal the staged values; no new migration, no `requirements` change, `frontend/` and `deploy/` untouched |
| 6 dry run | `deploy/prod/icb-deploy.sh <target> --dry-run` as icb (the expected blob) | plan = "DB migration no", "SPA rebuild no", "Service restart YES" |
| 7 deploy | `icb-deploy.sh <target> --yes` as icb: ff-only, restart, health | exit 0 and "DEPLOYED"; MainPID changed; `/var/tmp/icb-deploy-state` = `completed <target>` |
| 8 post-deploy | after 20 s | HEAD = target; `v1.59.2` local = the staged object; `git describe` = `v1.59.2` (what the header reads); alembic 0049; active; **the service started after the code moved**; **exactly 4** "Application startup complete" since the restart; **0** BOOTSTRAP FAILED; **0** tracebacks; health 200; PyYAML; the audit + correction tools import; `/openapi.json` local = LAN; the calculator page loads **`?v=184`** (exactly one tag); both doors serve the target `calculator.js`; the SPA unchanged |

Everything is logged under `/tmp/icb-release-v1.59.2/out-<mode>-<ts>/` and `/tmp/icb-rt1-data/out-<mode>-<X>-<ts>/`
(`run.log`, the dry-runs, the journals, `OUTCOME.txt`). The CA fetches them.

**The click-through (2g), on the domain, signed in:**

| check | expected |
|---|---|
| the page header | **v1.59.2** (also `/debug/health` → `"version": "v1.59.2"`) |
| FREEZER MEDIUM → **single door** | REAR FRAME & FLOOR PLATE reads **NOT SELECTED**; the eye shows its lines struck through, each reading **not used with SRD PU** |
| … → **double door** | REAR FRAME priced as before |
| … → **back to the door it opened with** | (the door toggle rewrites the Body Template's rear-door thickness — a known defect, queued; ending on the original door puts it back) |
| MEAT HANGER LARGE → **single door** | the SRD PU line ≈ **R1 463**, not ≈ R24 380 (after Manifest B); then back to its original door |
| Trailer Designer → a REAR FRAME card (any of the 14 bodies) | its rule chips read the database rule, marked **kept** |

## Expected audit movement (proved on the prod mirror — `docs/audit/rt1_2026-09/mirror/MIRROR_PROOF.md`)

Holds only if prod's pricing does not move between the 1b snapshot (30 Sep 16:28) and the window; the tool's guards
refuse the data if it did.

- **2a / 2c (before and after the code): identical** — the mirror priced 3 473 of 3 473 cells identically under
  v1.59.2 and under prod's own v1.59.0 reference. Expected counts:

  | pack | UNVERIFIABLE | ACCEPTED | PASS | SKIP |
  |---|---:|---:|---:|---:|
  | smoke | 9 | 18 | 171 | 36 |
  | chillers | 0 | 45 | 1 012 | 196 |
  | freezers | 27 | 33 | 522 | 108 |
  | icecream | 40 | 63 | 413 | 96 |
  | explosive | 36 | 155 | 385 | 108 |

- **2f (after A, then B):** the **57 SRD REAR FRAME & FLOOR PLATE cells go ACCEPTED → SKIP** (entry #5's R2 447–R10 502
  extra is gone; both sides are R0 — SKIP is the audit's status for "both zero", not PASS). Every other cell stays
  identical to the cent (3 416). With the default Manifest B, the 12 SRD cells that price 2415 / 3576 / 5585 move
  **+R1.78** each, status unchanged; the formula-only B moves nothing. Expected counts after A + B:

  | pack | UNVERIFIABLE | ACCEPTED | PASS | SKIP |
  |---|---:|---:|---:|---:|
  | smoke | 9 | 15 | 171 | 39 |
  | chillers | 0 | 17 | 1 012 | 224 |
  | freezers | 27 | 24 | 522 | 117 |
  | icecream | 40 | 55 | 413 | 104 |
  | explosive | 36 | 146 | 385 | 117 |

- **Manifest B's plan size** is the one RT1_RULING_1 picks: **7** (`manifest_b.yaml`, the dispatch default), **2**
  (`manifest_b_formula_only.yaml`, if the 29 Sep R4 095 is Burt's new price), or none (B stops). The staged
  `expected.env` pins it; any other plan is a `STOP [PLAN]`.

**For the OUTCOME, the rule reasons (BA-confirmed):** 13 bodies get `SRD EPS = N AND SRD PU = N`; **CHILLER LARGE
gets `SRD = N` (7233)** because on that body the door is a DOOR TYPE master and its SRD insulation radio stays ticked on
double-door quotes, so the pair would zero REAR FRAME on DRD. **ICECREAM BODY MEDIUM** gets Manifest A too: its
client-side folder exclusion already gives R0 on single-door quotes; the rule makes the server agree. Its section
vanishes instead of showing NOT SELECTED — a later cosmetic Trailer Designer tidy for Michael.

## Rollback (decided before the run; the code and the data rollbacks are independent)

- **Code:** back to `de74796` and restart. Either `sudo -u icb bash /opt/icb-platform/deploy/prod/icb-rollback.sh de74796`,
  or directly: `sudo -u icb git -C /opt/icb-platform reset --hard de74796` then `sudo systemctl restart icb-backend`.
  Re-probe the three doors. No SPA rebuild (frontend untouched), no migration to undo. The tag stays; the header then
  reads `v1.59.0` (prod has the tag after this fetch).
- **Data:** `sudo bash /tmp/icb-rt1-data/rt1_data.sh revert /var/backups/icb-rt1-2026-09/journal_B_<…>.json`, then the
  same for A's journal. The kit refuses A's revert while B is on prod. Each revert puts every journaled line back column
  for column, deletes the `bom_override_history` rows the apply wrote, and refuses if a line moved since. **Proved
  byte-exact on the prod mirror** (RT1_RETURN_1).
- **Last resort:** the step-4 dump `icb_platform_pre-v1.59.2_<ts>.dump` (the whole database before the window).

**After a STOP:**
- Code, before step 7: nothing on prod has changed (a backup file may exist). From step 7 on, re-running `release.sh
  deploy` resumes: at the target without a completion record, `icb-deploy.sh` re-runs its idempotent steps —
  `alembic upgrade head` (a no-op at 0049), **`npm run build`** (`frontend/` is unchanged, so the same bundle; the kit
  asserts the bundle name did not change) and the restart — and every assert runs again.
- Data: a dry-run or apply STOP writes nothing (one transaction, guards before any write). An `AFTER` STOP means the
  apply committed but the second dry-run still found work: tell the CA before anything else.
- A `BOOTSTRAP FAILED` is the known worker race; one more restart normally heals it.

## Simulation (WSL, 30 Sep; the real `icb-deploy.sh`, the real `mkstage.sh` / `mkstage_data.sh`)

**Code kit** (`/root/relsim2-*`: fake prod at `de74796` without the `v1.59.0` tag; sim origin = the release branch + a
real annotated `v1.59.2`). The kit's `release.sh` is identical at every target the runs used (`f6df558` / `42852d6`).

| scenario | result |
|---|---|
| happy | preflight PASS → `verify` fails on exactly the 6 (`HEAD`, `TAG_LOCAL`, `DESCRIBE` v1.50.0, `TEMPLATE_V` 182, `CALC_LOCAL`, `CALC_LAN`) and passes 12 → deploy **DEPLOYED** (the fetch brings `v1.59.0` + `v1.59.2`; `git describe` = v1.59.2; 4 workers; the service started after the code moved) → `verify` 0 failures → deploy again = **ALREADY DEPLOYED**. No root-owned `__pycache__` left in the repo |
| tag not on origin | preflight fails `TAG_ON_ORIGIN` only → deploy **STOP [TAG]** after the fetch (nothing else moved) |
| prod moved by hand | **STOP [ANCHORS]**; and `verify` then also fails `RESTART_AFTER_CODE` (the code moved after the service started — the half-deploy signature: a known hit for that check) |
| a worker logs BOOTSTRAP FAILED | `icb-deploy.sh` fails → **STOP [DEPLOY]** naming the anchor and the backup; `verify` shows `BOOTSTRAP_FAILED = 1` |
| a traceback after the restart | **STOP [TRACEBACKS]**, with the journal excerpt; a later `verify` / re-run stops on it too (it used to report green) |
| the doors serve old calculator bytes after the restart | **STOP [CALC_LOCAL]** |
| the restart fails after the fast-forward | **STOP [DEPLOY]** → re-run = **RESUME** → DEPLOYED → `verify` 0 failures → ALREADY DEPLOYED |

The simulation found three kit defects before any prod use, all fixed: whole-second service-start arithmetic (a correct
restart in the same second as the fast-forward could read as a half-deploy); a 5 s journal margin that counted the
previous start's workers; tracebacks checked only inside `deploy`.

**Data kit** (`/root/relsim3-*`: the real `rt1_data.sh` over a stand-in for the correction tool that keeps its output
contract; a stand-in Manifest B of 7 entries) — **14 of 14**: dry-run A = 120 to apply; **apply B before A → STOP [ORDER]**;
apply A → journal + pre-apply backup + provenance kept in `/var/backups/icb-rt1-2026-09/`, second dry-run clean; apply A
again → already applied; dry-run / apply B; **revert A while B is on → STOP [ORDER]**; revert B; revert A; revert A again →
**STOP [REVERT]**; a guard mismatch → **STOP [GUARD]**; a plan of the wrong size → **STOP [PLAN]**; a tampered manifest →
**STOP [KIT]**; prod's code moved → **STOP [CODE]**. The real tool's behaviour (guards, one transaction, byte-exact
revert) is proven on the prod mirror.

## After the window (RT1 Stage 3)

Prune entry #5 from `accepted_differences.prod.yaml` alone, then `audit reaccept --env prod` on the 2f reports; the
prod baseline paste (`rt1_snapshot.sh`, mode `baseline`) regenerates the CI snapshot, committed with the pruned list;
the OUTCOME docs PR merges when CI is green on its exact head; Michael removes the `/tmp` staging on the VM.

## OUTCOME

*(Appended after the run.)*
