# Prod deploy: v1.60.0 (RT3) — body families in colour: the code release, then the six families, in one window

**Status:** prepared for `RT3_RULING_2` (nothing on prod until then). Prod today: **v1.59.3 = `0926193`**, alembic
**0050**. Michael runs every prod step; the CA's own writes to the VM are refused (correctly).

## What ships

- **Migration 0051** (`0051_trailer_group_colour_order.py`): `trailer_groups.colour` (`#RRGGBB`, CHECK
  `ck_trailer_groups_colour`) and `trailer_groups.sort_order` (`INTEGER NOT NULL DEFAULT 100`). Schema only, additive,
  inspector-guarded, up → down → up clean. Every group reads colour NULL / order 100 after it.
- **The fixed startup bootstrap** (RT3_RULING_1 Q3, G1): a seed's group is found by its name **or** its template and is
  created only together with the template (a fresh database). After the families, MEATHANGER is MEAT and the
  RHINORANGE group is gone; before this fix the next restart would have brought both back.
- **The families on the MES screens** (RT3_RULING_1a: the light MES skin only): the BODY TYPE optgroups, options in the
  family ink, the closed box's family bar + tooltip, the top-bar chip; chips on the costings list and the saved
  costing; Admin → Quote templates edits colour / order / name and moves bodies (admin-only in the API); a required
  Family select on the Trailer Designer's new-body form.
- **An SPA rebuild** (`frontend/` changed: the costings list and saved-costing chips). `package.json` is unchanged:
  `npm run build` only, nothing installed.
- **The six families are DATA**, set by `ops/prod-rt3/rt3_families.sh` after the deploy (not by the migration).

No price, formula, BOM row or quote document changes. Every active body prints the same quote template before and
after (the template guard, below).

## The kits (committed, staged byte-exact from the merge commit)

| kit | staged by | runs |
|---|---|---|
| `icb-release-v1.60.0` | `bash ops/prod-release-v1.60.0/mkstage.sh <out> <merge-sha>` | `release.sh preflight / verify / deploy` |
| `icb-rt3-families` | `bash ops/prod-rt3/mkstage_window.sh <out> <merge-sha>` (after the tag) | `rt3_families.sh dryrun / apply / revert` |
| `icb-rt2-all` | the same `mkstage_window.sh` (RT2's kit, unchanged; v1.59.3 **or** v1.60.0, alembic 0050 or 0051) | `rt2_all.sh pre / post` |
| `icb-rt2-doors` | the same | `rt2_doors.sh` (14 OK) |

## Sequence

**0. Michael picks the window.** About 45 min. The restart is a few seconds of outage; the migration adds two
columns to a 4-row table (instant); the SPA build takes about a minute (the old bundle keeps serving meanwhile).

**1. Merge, tag, stage (after RT3_RULING_2).**
- CI green on the PR's exact head → Michael's merge word → squash-merge into `backport/v1.39-base`. The merge commit
  is the target; its tree must equal the CI-tested tree.
- The CA tags it: `git tag -a v1.60.0 <merge-sha> -m "…"`, `git push origin v1.60.0`, and proves the **tag object** on
  origin equals the local one (`git ls-remote --tags origin v1.60.0`), peeled = the merge commit.
- The CA stages the kits from the merge commit: `mkstage.sh <out> <merge-sha>` and `mkstage_window.sh <out> <merge-sha>`.
- Michael copies them. From Windows PowerShell:
  - `scp "<out>\icb-release-v1.60.0.tar" "<out>\icb-rt3-families.tar" "<out>\icb-rt2-all.tar" "<out>\icb-rt2-doors.tar" mickeyger@192.168.0.251:/tmp/`
  - `ssh mickeyger@192.168.0.251 "cd /tmp && tar -xf icb-release-v1.60.0.tar && tar -xf icb-rt3-families.tar && tar -xf icb-rt2-all.tar && tar -xf icb-rt2-doors.tar"`

**2. Preflight + the known-hit check (read only, any time before the window).** On the VM:

```
sudo bash /tmp/icb-release-v1.60.0/release.sh preflight
sudo bash /tmp/icb-release-v1.60.0/release.sh verify
```

(From Windows: `ssh -t mickeyger@192.168.0.251 "sudo bash /tmp/icb-release-v1.60.0/release.sh preflight"`; `-t` lets
sudo prompt; do not pipe it.)

- `preflight` asserts:
  - db `icb_platform`, alembic 0050, HEAD `0926193`, no tracked modifications;
  - **the 0051 columns are absent**; it prints today's groups and the bindings fingerprint;
  - each page loads its v1.59.3 `?v=` (calculator 185, calculator2 127, admin_templates 19, theme-mes 6), both doors
    serve the v1.59.3 blob under it, and `body_family.js` is not loaded yet;
  - the SPA served = disk on both doors, and it does **not** yet carry the family chip;
  - health 200; PyYAML 6.0.2; npm present for icb and `frontend/node_modules` present (the build needs both);
  - **the `v1.60.0` tag object is on origin**; the backup directory is writable;
  - `deploy/prod/icb-deploy.sh` is the expected blob, and icb's sudo is NOPASSWD.
- `verify` before the deploy **must fail on exactly 23 checks** (the simulation's list) and pass the rest:
  - `HEAD`, `TAG_LOCAL`, `DESCRIBE` (`v1.59.3` today), `ALEMBIC` (0050), `COLUMNS`, `CHECK_CONSTRAINT`;
  - `V_` / `LOCAL_` / `LAN_` for each of the five files (calculator, calculator2, admin_templates, theme-mes: the old
    `?v=` and blob; body_family: not loaded yet, and not served under `?v=1`);
  - `SPA_HAS_FAMILY_LOCAL` / `_LAN` (the v1.59.3 bundle has no family chip);
  - `TRACEBACKS` counts since the current service start (2 Oct 11:11). If prod has logged an error since, it fails too
    and prints the excerpt: pre-existing, report it, it does not block.

**3. The window** (RT3_RULING_1 addition 2, in this order).

| # | who | step | pass condition |
|---|---|---|---|
| a | Michael | Admin → Costing audit → **All**; when finished, `sudo bash /tmp/icb-rt2-all/rt2_all.sh pre` | `PAGE = CLI`; 0 FLAG (prod as RT2 closed) |
| — | Michael | `sudo bash /tmp/icb-release-v1.60.0/release.sh deploy` | `######## DEPLOYED`: every step below; `GROUPS_UNCHANGED`, `BINDINGS_UNCHANGED`, `FAMILIES_NOT_YET` = 0, the SPA rebuilt and carrying the chip |
| — | CA | the Cloudflare door, from outside, **only now** | `mes.icecoldgrp.online`: the five files at their new `?v=` = the target blobs; the new SPA bundle; `/openapi.json` = the LAN door |
| b | Michael | `sudo bash /tmp/icb-rt3-families/rt3_families.sh dryrun` → `… apply` | dry-run **40 to apply, 0 already applied** and **TEMPLATE GUARD: 16 of 16 active bodies keep their resolved template; changed: [11, 22, 23, 28, 29, 30, 31, 32, 33, 35]** (the Q5 soft-deleted copies) → applied in one transaction, journal kept → second dry-run **0 to apply, 40 already applied** |
| c | Michael | **the template proof**: preview one quote document each — an EXPLOSIVE body, a FREEZER, a MEAT HANGER, **RHINORANGE TRAILER** (its own override) and a CHILLER | each prints its usual template: explosive / freezer / meathanger / rhinorange / the default document |
| d | Michael | Costings → **New Costing** (the MES screen) → the BODY TYPE box | six optgroups, in order EXPLOSIVE, CHILLER, FREEZER, MEAT, ICE CREAM, OTHER (then the REPAIRS divider); picking a body shows its family's bar on the closed box and the family chip in the top bar |
| e | Michael | Admin → Quote templates (from the MES calculator's sidebar, so the MES skin): change one family's colour (e.g. ICE CREAM to `#C12E77`) → Save; check the calculator and the costings list; then **set it back to the approved hex** | the new colour shows on the BODY TYPE box and the costings list chip; a too-light colour (e.g. `#38BDF8`) warns and asks — Cancel saves nothing |
| f | Michael | **restart once more**: `sudo systemctl restart icb-backend`, then `sudo bash /tmp/icb-rt3-families/rt3_families.sh dryrun` and `sudo bash /tmp/icb-release-v1.60.0/release.sh verify` | the dry-run reads **0 to apply, 40 already applied** (the families and RHINORANGE's override survived the bootstrap); verify: 0 failed, `BOOTSTRAP_SEEDED_GROUPS` = 0 |
| g | Michael | `sudo bash /tmp/icb-rt2-doors/rt2_doors.sh` | **SUMMARY: 14 OK** |
| a′ | Michael | **All** again → `rt2_all.sh post` | `PAGE = CLI`; the page reads **No change** against (a): nothing priced moved |

The standalone `/calculator` (the old dark stylesheet) shows the optgroups but no colours: the families are built for
the MES skin only (RT3_RULING_1a). Sales use the MES screen.

`release.sh deploy`, step by step:

| step | what | asserted |
|---|---|---|
| 1 anchors | the start state | HEAD `0926193` + alembic 0050 (fresh); or HEAD = target with 0050 or 0051 (resume); or HEAD = target + 0051 + the completion record (already deployed: asserts only). No tracked modifications; rollback anchor written |
| 2 bytes before | the served baseline | each page's v1.59.3 `?v=` and blob on both doors; `body_family.js` not loaded; SPA served = disk |
| 3 groups before | the baseline the restart must keep | the groups (`id:name:template`) and the md5 of every body's `id:group:override` |
| 4 PyYAML | present | 6.0.2 (nothing is installed) |
| 5 **backup** | `pg_dump -Fc` → `/var/backups/postgres/icb_platform_pre-v1.60.0_<ts>.dump` (mode 600) | size > 0, sha256 printed; `pg_restore --list` has TABLE DATA incl. `alembic_version`, `trailer_groups`, `trailer_types`. **The rollback for 0051** |
| 6 fetch + guards | `git fetch origin --tags` as icb | origin = the staged target; the tag object, peeled, `git describe` = `v1.60.0`; `0926193` an ancestor; changed-file count + C-sorted sha256 = staged; **exactly one new migration = 0051**; no dependency manifest changed; `frontend/` changed (the rebuild); `deploy/` untouched |
| 7 dry run | `icb-deploy.sh <target> --dry-run` as icb | "DB migration YES - 0051_trailer_group_colour_order.py", **"SPA rebuild YES"**, "Service restart YES", no dependency warning |
| 8 deploy | `icb-deploy.sh <target> --yes`: its own backup, ff-only, alembic upgrade head, **npm run build**, restart, health | exit 0, "DEPLOYED"; MainPID changed; the completion record |
| 9 post-deploy | after 20 s | HEAD, tag, describe; **alembic 0051, both columns as the migration writes them, the CHECK**; active; started after the code moved; 4 workers; 0 BOOTSTRAP FAILED; **0 "Seeded TrailerGroup"**; 0 tracebacks; health; PyYAML; tools import; `/openapi.json` local = LAN; **the five files at their new `?v=` (186 / 128 / 20 / 1 / 7) with the target blobs on both doors**; the SPA served = disk, **renamed and carrying `trailer_family` on both doors**; **the groups and every binding exactly as before**; 0 families coloured yet |

Everything is logged under `/tmp/icb-release-v1.60.0/out-<mode>-<ts>/`, `/tmp/icb-rt3-families/out-<mode>-<ts>/`,
`/tmp/icb-rt2-all/out-<label>-<ts>/` and `/tmp/icb-rt2-doors/out-<ts>/`. The journals and the pre-apply backup stay in
`/var/backups/icb-rt3-2026-10/`.

## The family plan (the dry-run's before → after; rehearsed on the local mirror topped up to prod's 41 bodies)

| family (order) | colour | group | template | active bodies |
|---|---|---|---|---|
| 1 EXPLOSIVE | `#E03131` | #1 EXPLOSIVE | explosive_quote | EXPLOSIVE UP TO 2.7, 2.7 TO 4.8, 4.9 AND UP |
| 2 CHILLER | `#168ED9` | NEW | none (the default document, as today) | CHILLER 2.3 METER, MEDIUM, LARGE |
| 3 FREEZER | `#4263EB` | #4 FREEZER | freezer_quote | FREEZER 2.3 METER, MEDIUM, LARGE |
| 4 MEAT | `#D66A0B` | #3 MEATHANGER → **MEAT** | meathanger_quote | MEAT HANGER LARGE, SMALL-MEDIUM |
| 5 ICE CREAM | `#D63384` | NEW | none | ICECREAM BODY SMALL, MEDIUM, LARGE |
| 6 OTHER | `#7D858C` | NEW | none | Manni RIGIDS CB, **RHINORANGE TRAILER** (its own override → rhinorange_quote) |

40 changes: 3 group updates, 3 new groups, 32 body moves (inactive bodies included: nothing is ever uncoloured), 1
override, 1 delete (the empty RHINORANGE group). The 10 soft-deleted copies move from the default document to their
family's template (RT3_RULING_1 Q5: 0 saved costings, hidden everywhere).

## Rollback (decided before the run)

**Data first, then code** — the v1.59.3 code carries the OLD bootstrap, which would re-create MEATHANGER and RHINORANGE
on its first start if the families were still on.
- **The families:** `sudo bash /tmp/icb-rt3-families/rt3_families.sh revert /var/backups/icb-rt3-2026-10/journal_families_<…>.json`
  → every row back (the RHINORANGE group with its own id 2); the dry-run reads **40 to apply** again.
- **The code:** back to `0926193`: `sudo -u icb git -C /opt/icb-platform reset --hard 0926193`, then the SPA
  (`sudo -u icb bash -lc 'cd /opt/icb-platform/frontend && npm run build'` — frontend changed in this range), then
  `sudo systemctl restart icb-backend`. Re-probe the doors.
  - **0051 stays** (additive; `icb-deploy.sh` never downgrades). The v1.59.3 code does not read the two columns.
- **The full restore** (only if both of the above fail): the step-5 dump.

## Simulation (WSL; the real `icb-deploy.sh`, the real `mkstage*.sh`)

- `ops/prod-release-v1.60.0/sim/run_all.sh`: happy · notag · moved · bootfail · traceback · stalecache · resume ·
  migfail · nobackup · **nobuild** (the SPA build produced nothing new) · **groupseeded** (the restart seeds a group).
- `ops/prod-rt3/sim/run_families_sim.sh`: the window sequence (dry-run before the deploy stops; dry-run; apply; apply
  again; the restart check; revert; revert again; re-apply) and the guards (a moved row, prod moved since the
  discovery, the plan's size, the guard's set, the apply's own guard, a tampered tool, prod's code moved).

## OUTCOME

(to be written after the window)
