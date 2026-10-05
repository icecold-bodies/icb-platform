# Prod deploy: v1.60.1 (RT4): move into an existing section, deny-by-default sign-in, Manifest S, in one window

**Status: RUN 5 Oct 2026, 08:53–09:01 SAST — DEPLOYED, see the OUTCOME at the end.** This runbook was committed
before the run; the OUTCOME is appended after it.
(Before: v1.60.0 = `682a6cc`, alembic 0051.) Michael runs every prod step. The CA stages the kits and reads the
records back.

## What ships

**Part A: "Move into existing section" and honest renames (RT4_RULING_1 Q4–Q6)**
- `services/sections.py` is the one place that answers "who uses this section". It also holds the one row move (FK id
  and legacy string together) and the A2 draft rule.
- New admin-only endpoints:
  - `GET /api/bom-sections/usage`
  - `GET /api/bom-sections/{id}/usage[?rename_to=]`
  - `POST /api/bom-sections/{id}/move-body-lines`
- **Body Templates:**
  - a **Sections…** list, which also reaches a section no body uses any more;
  - the Edit-section dialog says who uses the section;
  - a name that already exists, in any case, offers to **move this body's lines** into it, with price-effect notes;
  - a plain rename of a shared section warns first and names the bodies;
  - an emptied section offers "Delete: no body uses it any more".
- The **Configurator (preview)** rename gets the same warning.
- Both global renames re-key every Settings-page draft that names the old section, unless that draft already has the
  new name; such a draft is left and reported.
- A rename to an existing name in any case is refused. That closes the near-twin hole, which the journey's negative
  control demonstrated.
- `admin_templates.js?v=21`.

**Part C: deny by default (Q7–Q9)**
- One app-wide dependency, `deps.require_session_unless_public`, runs on every route. The only public ones are `/`,
  `/login` (GET/POST), `/login/change-password`, `/logout`, `/health`, `/health/version`, `/debug/health/ping` and the
  `/mes-app` shell (static and SPA assets are mounts and stay public).
- `/api/mes/autologin` is public only where it is mounted (never on prod).
- `/docs`, `/redoc` and `/docs/oauth2-redirect` are **off**. `/openapi.json` is **admin-only**.
- **`GET /health/version`** returns `{"version": "<tag>"}` and nothing else. It replaces every kit's use of
  `/openapi.json`.
- With no session: `/api/*` (or `Accept: application/json`) gets **401**; a page goes to `/login?next=<page>`.

**Manifest S: data, after the deploy (Q2 + Q3)**
- 46 line moves, with `bom_section_id` and `bom_section` changed together and each guarded on its exact current id
  **and** string:
  - MANNI DF's 7 drifted lines → the section their string names;
  - deleted id 41's 39 lines → 26 / 15 / 21.
- id 41's own draft is re-keyed (2 keys); its snapshot is never touched.
- `expect_unused_after [83, 84, 85]` is a **STOP** if anything else still names them.
- Mirror proof: 36 pricings identical to the cent, line by line, before S, after S and after revert.

**No migration, no dependency, no SPA rebuild: a restart.** No price, formula or rule changes. No Manni is activated.
id 41 stays deleted.

## The kits (committed, staged byte-exact from the merge commit)

| kit | staged by | runs |
|---|---|---|
| `icb-release-v1.60.1` | `bash ops/prod-release-v1.60.1/mkstage.sh <out> <merge-sha>` | `release.sh preflight / verify / deploy` |
| `icb-rt4-data` | `bash ops/prod-rt4/mkstage_window.sh <out> <merge-sha>` (after the tag) | `rt4_data.sh dryrun / apply / revert` |
| `icb-rt2-all` | the same `mkstage_window.sh` (v1.60.0 **or** v1.60.1; C11 also reads `/var/backups/icb-rt4-2026-10`) | `rt2_all.sh pre / post / afterS` |
| `icb-rt2-doors` | the same | `rt2_doors.sh` (14 OK) |

## Sequence

**0. Michael picks the window.** It takes about 40 minutes. The restart means a few seconds of outage. There is no
migration and no build.

**1. Merge, tag, stage (after RT4_RULING_2).**
- CI green on the PR's exact head → Michael's merge word → squash-merge into `backport/v1.39-base`. The merge commit
  is the target, and its tree must equal the CI-tested tree.
- The CA tags it:
  - `git tag -a v1.60.1 <merge-sha> -m "…"`, then `git push origin v1.60.1`;
  - then proves the **tag object** on origin equals the local one (`git ls-remote --tags origin v1.60.1`), peeled =
    the merge commit.
- The CA stages the kits from the merge commit: `mkstage.sh <out> <merge-sha>` and
  `mkstage_window.sh <out> <merge-sha>`.
- Michael copies them. From Windows PowerShell:
  - `scp "<out>\icb-release-v1.60.1.tar" "<out>\icb-rt4-data.tar" "<out>\icb-rt2-all.tar" "<out>\icb-rt2-doors.tar" mickeyger@192.168.0.251:/tmp/`
  - `ssh mickeyger@192.168.0.251 "cd /tmp && tar -xf icb-release-v1.60.1.tar && tar -xf icb-rt4-data.tar && tar -xf icb-rt2-all.tar && tar -xf icb-rt2-doors.tar"`

**2. Preflight and the known-hit check (read only, any time before the window).** On the VM:

```
sudo bash /tmp/icb-release-v1.60.1/release.sh preflight
sudo bash /tmp/icb-release-v1.60.1/release.sh verify
```

`preflight` asserts:
- db `icb_platform`, alembic 0051, HEAD `682a6cc`, no tracked modifications;
- Body Templates loads `admin_templates.js?v=20`, and both doors serve the v1.60.0 blob under it;
- the SPA served = disk on both doors; health 200; PyYAML 6.0.2;
- **the `v1.60.1` tag object is on origin**; the backup directory is writable;
- `deploy/prod/icb-deploy.sh` is the expected blob, and icb's sudo is NOPASSWD.

It also **prints, for the record, what each door answers today with no session**. Before the deploy those are the
open routes.

`verify` before the deploy **must fail on exactly 14 checks** (the simulation's list) and pass the rest:
- `HEAD`, `TAG_LOCAL`, `DESCRIBE` (`v1.60.0` today);
- `TOOL_IMPORT`: `app.services.sections` does not exist yet;
- `VERSION_LOCAL` / `_LAN` / `_CF`: `/health/version` is a 404 today;
- `NOAUTH_LOCAL` / `_LAN` / `_CF`: today's open routes answer 200 where they must answer 401;
- `TEMPLATE_V` (20), `STAT_LOCAL` / `STAT_LAN` (the v1.60.0 blob), `PREVIEW_TEMPLATE` (no warning text yet).

`TRACEBACKS` counts since the current service start (3 Oct 06:12). If prod has logged an error since then, that check
fails too and prints the excerpt. That error is pre-existing: report it, but it does not block.

**3. The window** (RT4_RULING_1, in this order).

| # | who | step | pass condition |
|---|---|---|---|
| 1 | Michael | Admin → Costing audit → **All**; when finished, `sudo bash /tmp/icb-rt2-all/rt2_all.sh pre` | `PAGE = CLI` |
| 2 | Michael | `sudo bash /tmp/icb-release-v1.60.1/release.sh deploy` | `######## DEPLOYED`. Every post-deploy assert passes, **including the three doors**: `VERSION_LOCAL/LAN/CF` = `v1.60.1`, and `NOAUTH_LOCAL/LAN/CF` = "all 44 as expected" |
| 3 | Michael | **All** → `rt2_all.sh post` | `PAGE = CLI`; the page reads **No change** against step 1 (the Mannis are in no pack) |
| 4 | Michael | `sudo bash /tmp/icb-rt4-data/rt4_data.sh dryrun` → `… apply` | dry-run **46 to apply, 0 already applied** · **drafts: 2 to apply, 0 already applied** · `expect_unused_after [83, 84, 85]: no other line or draft names them`. Applied in one transaction, journal + backup kept in `/var/backups/icb-rt4-2026-10/`. The kit's own second dry-run reads **0 to apply, 46 already applied** and "they are unused now" |
| 5 | Michael | **All** → `rt2_all.sh afterS` | `PAGE = CLI`; **No change** (C11: the page run must start after S's journal) |
| 6 | Michael | **Part A live acceptance** (no test data on prod): Body Templates → **Sections…** → filter "FITTINGS" / "REAR" → open **DOOR FITTINGS SRD**, **DOOR FITTINGS DRD**, **REAR FRAME + FLOOR PLATE** | each dialog reads "No body uses it any more." and its button reads **Delete: no body uses it any more** → Delete. All three are then gone from the Sections list and from the BOM-section dropdown. **If any of them shows "Shared: used by …", STOP and tell the CA** |
| 7 | Michael | `sudo bash /tmp/icb-rt2-doors/rt2_doors.sh` | **SUMMARY: 14 OK** |
| 8 | Michael | `sudo bash /tmp/icb-release-v1.60.1/release.sh verify` (the three-door probe again, after the data) | **0 failed**: no session → 401 on every closed route on 127.0.0.1, the LAN and Cloudflare; `/health` and `/health/version` answer; version **v1.60.1** on all three |
| 9 | Michael | click-through: Body Templates → **MANNI DF**; then a **sales** login → Costings → New → price any body | MANNI DF's 7 lines show unchanged under **3MM MILD STEEL FLOOR** / **LOAD LOCK RAILS**; the sales user prices normally |

`release.sh deploy`, step by step:

| step | what | asserted |
|---|---|---|
| 1 anchors | the start state | HEAD `682a6cc` + alembic 0051 (fresh); or HEAD = target (resume); or HEAD = target + the completion record (already deployed: asserts only). No tracked modifications; rollback anchor written |
| 2 bytes before | the served baseline | `admin_templates.js?v=20` and its blob on both doors; SPA served = disk |
| 3 PyYAML | present | 6.0.2 (nothing is installed) |
| 4 **backup** | `pg_dump -Fc` → `/var/backups/postgres/icb_platform_pre-v1.60.1_<ts>.dump` (mode 600) | size > 0, sha256 printed; `pg_restore --list` has TABLE DATA incl. `bill_of_materials`, `configurator_drafts`, `bom_sections` |
| 5 fetch + guards | `git fetch origin --tags` as icb | origin = the staged target; the tag object, peeled, `git describe` = `v1.60.1`; `682a6cc` an ancestor; changed-file count + C-sorted sha256 = staged; **no migration**, no requirements, `frontend/` and `deploy/` untouched |
| 6 dry run | `icb-deploy.sh <target> --dry-run` as icb | "DB migration no", "SPA rebuild no", "Service restart YES" |
| 7 deploy | `icb-deploy.sh <target> --yes`: ff-only, restart, health | exit 0, "DEPLOYED"; MainPID changed; the completion record |
| 8 post-deploy | after 20 s | HEAD, tag, describe; alembic 0051; active; started after the code moved; 4 workers; 0 BOOTSTRAP FAILED; 0 tracebacks; health; PyYAML; the tools import (incl. `app.services.sections`); **`/health/version` = v1.60.1 on 127.0.0.1, LAN, Cloudflare**; **every line of `probe_paths.txt` answers its status with no session on all three doors** (35 × 401, 3 × 404 docs off, the public 6); `admin_templates.js?v=21` = the target blob on both doors; the preview template carries the shared-rename warning; the SPA unchanged |

Everything is logged under `/tmp/icb-release-v1.60.1/out-<mode>-<ts>/`, `/tmp/icb-rt4-data/out-<mode>-S-<ts>/`,
`/tmp/icb-rt2-all/out-<label>-<ts>/` and `/tmp/icb-rt2-doors/out-<ts>/`.

## Behaviour a user can notice

- **With no session:**
  - an `/api` call gets 401;
  - a page or an export link goes to the login page, then straight back (`?next=`);
  - before, a few exports answered a raw 401, and 32 data routes answered with data.
- **The kits and the RT habit:** "the best prod proof is an unauthenticated `/openapi.json`" is **retired**. Use
  `/health/version`: the new Python is live when every door reads the new tag.

## Rollback (decided before the run)

**Data first, then code.**

**Manifest S:** `sudo bash /tmp/icb-rt4-data/rt4_data.sh revert /var/backups/icb-rt4-2026-10/journal_S_<…>.json`.
Every line and id 41's draft go back; the dry-run then reads **46 to apply** again.
- **If step 6 already deleted 83/84/85**, the revert's lines would point at sections that no longer exist. Put the
  three rows back first, with their prod ids and values (`discovery_20261004-080150`), in one statement:
  `INSERT INTO icb_costings.bom_sections (id, name, sort_order, multiplier, is_optional) VALUES (83, 'DOOR FITTINGS SRD', 2, 1.0, false), (84, 'DOOR FITTINGS DRD', 4, 1.0, false), (85, 'REAR FRAME + FLOOR PLATE', 10, 1.0, false);`
  Then revert.

**The code:** back to `682a6cc`:
- `sudo -u icb git -C /opt/icb-platform reset --hard 682a6cc`, then `sudo systemctl restart icb-backend`. No SPA
  build: `frontend/` is unchanged in this range.
- Then `release.sh verify` from the v1.60.0 kit, or a probe: `/openapi.json` answers again, and `/health/version`
  is 404.
- S's data is compatible with the v1.60.0 code: it only moved lines between existing sections.

**The full restore** (only if both of the above fail): the step-4 dump.

## Simulation (WSL; the real `icb-deploy.sh`, the real `mkstage*.sh`)

| kit | scenarios | result |
|---|---|---|
| `ops/prod-release-v1.60.1/sim/run_all.sh` | happy · notag · moved · bootfail · traceback · stalecache · resume · stillopen (a route stays open) · cfstale (Cloudflare still on v1.60.0) · nobackup | see `RT4_RETURN_2` |
| `ops/prod-rt4/sim/run_data_sim.sh` | the window sequence + every STOP (unused, guard, plan, alembic, app, kit, code, foreign journal) | 16 / 16 |
| `ops/prod-rt4/sim/run_window_sim.sh` | stager before/after the tag; All pre/post/afterS; doors; C11 against the RT4 journal | 11 / 11 |
| `ops/prod-rt2/sim/run_all_sim.sh` (RT2's, against the edited `rt2_all.sh`) | unchanged behaviour by default | 16 / 16 |

## OUTCOME

**PROD = v1.60.1 = `01751fa`**:
- **tag:** object `e9b6327`; local = origin, peels to `01751fa`;
- **schema:** alembic **0051** (no migration);
- **deployed:** 5 Oct 2026 08:56 SAST by Michael's `release.sh deploy`;
- **restore point:** `icb_platform_pre-v1.60.1_20261005-085605.dump` (3 134 567 bytes, sha256 `8d65ca3f…`).

**Manifest S applied** 08:58. **Nothing priced moved.** The evidence is under `docs/audit/rt4_2026-10/prod/`.

### Before the window (RT4_RULING_2's read-only check, 08:19): `prewindow_20261005-081925/`

- **Release checks:** `release.sh preflight` PASSED. `verify` failed on exactly the 14 expected checks; TRACEBACKS 0.
- **(a) What changed:**
  - **Michael's removals** (no PU on the chillers; EPS only on ROOF + FLOOR on the freezers) are **draft nodes only**,
    saved 29 Sep – 2 Oct, before the 3 Oct baseline. No master was deleted.
  - **Since 3 Oct,** there are hand edits to prices, lines and formulas on the icecream, explosive, FREEZER MEDIUM (a
    cap swap with no price effect) and RHINORANGE bodies. They are listed in `facts.txt`, and they are not RT4's.
- **(b) Manifest A:** OK on all 14 bodies, through the engine.
- **(c) The door report:** 14 OK.
- **(d) Audit cells:** 156 of 2 702 moved since page run #33 (explosive 108, icecream 48), none from the removals. Today
  = page run #36 (PASS 1 987 · ACCEPTED 136 · FLAG 0).

### The window (5 Oct): `window_20261005/`

| # | step | result |
|---|---|---|
| 1 | All #37 → `rt2_all.sh pre` | first try **STOP [PAGE]** (the newest run was older than 45 min); after All: **PAGE = CLI**, 2 702 / 2 702 |
| 2 | `release.sh deploy` 08:56:05 → 08:56:54 | **DEPLOYED**. Every assert PASS: version **v1.60.1** on 127.0.0.1, LAN and Cloudflare; no-session probe **all 44 as expected** on all three doors; `?v=21` + target blob on both doors; the preview warning present; the SPA unchanged |
| 3 | All #38 → `post` | **PAGE = CLI**, same counts |
| 4 | `rt4_data.sh dryrun` → `apply` | **46 to apply · drafts: 2** → APPLIED (journal `/var/backups/icb-rt4-2026-10/journal_S_…065813Z.json`, backup `pre_apply_S_…sql.gz`). Second dry-run: **0 to apply, 46 already applied · drafts 2 already · 83/84/85 unused now** |
| 5 | All #39 → `afterS` | **PAGE = CLI**, same counts. C11 used S's journal |
| 6 | Sections… → delete DOOR FITTINGS SRD / DOOR FITTINGS DRD / REAR FRAME + FLOOR PLATE | **Done on prod at the close (12:40–12:44)**. The first attempt, in the window, was made in a browser on ANOTHER server. See the close check below |
| 7 | `rt2_doors.sh` | **SUMMARY: 14 OK** |
| 8 | `release.sh verify` | **0 checks failed** |
| 9 | click-through | MANNI DF's 7 lines under 3MM MILD STEEL FLOOR (4) and LOAD LOCK RAILS (3), at the top of its list (sort 0); a sales user prices normally; **CHILLER MEDIUM offers no PU**; **FREEZER MEDIUM offers EPS on the roof and floor only** |

**No change, cell by cell** (`cells_window_identical.txt`): 2 936 of 2 936 cells over the five packs are identical
across the pre-window run, All pre, post (after the deploy) and afterS (after S).

### Step 6's evidence: the close check (read-only, BA addition), in `close_20261005/`

1. **12:33, `close_check_20261005-123324.txt`:** bom_sections **83, 84 and 85 still existed**, even though Michael had
   deleted all three in the window. The rest was as expected: no line and no draft named them; MANNI DF's 7 lines on
   64 / 65; id 41's 39 lines on 26 × 17, 15 × 13, 21 × 9. The `/tmp` kits were removed in the same run.
2. **12:39, `step6_diag_20261005-123935.txt`** (`rt4_step6_diag.sh`, read only):
   - prod's service log has **no DELETE / PUT / POST on `/api/bom-sections` since 08:50**, and no read of the
     Sections list. The deletes had been made in a browser tab on another server;
   - no error since the window;
   - the only foreign keys onto `bom_sections` are `bill_of_materials` (0 rows on 83–85) and `body_option_groups`
     (none on 83–85), so nothing blocks the delete.
3. **12:40–12:44:** step 6 was redone on prod (`mes.icecoldgrp.online` / `192.168.0.251` → Body Templates →
   Sections…).
4. **12:44, `close_check_20261005-124452.txt`:**
   - **83, 84 and 85 are gone; 15 (DRD DOOR FITTINGS), 21 (REAR FRAME & FLOOR PLATE) and 26 (SRD DOOR FITTINGS)
     exist.**
   - Lines naming them: 0. Drafts naming them: 0.
   - S1: 793–796 on 64 and 843–845 on 65. S2: 26 × 17, 15 × 13, 21 × 9.

**`/tmp` on the VM:** every RT4 kit folder and tar is removed (`rt4_close.sh`). What stays are older files that are not
RT4's: the v1.52 scripts of 7 Sep, `icb-deploy.sh`'s rollback anchors, and `icb-srd-discovery`. Kept on purpose:
`/var/backups/postgres/icb_platform_pre-v1.60.1_20261005-085605.dump` and `/var/backups/icb-rt4-2026-10/` (S's journal,
provenance and pre-apply backup).

**Rollback from now on:** reverting S needs 83 / 84 / 85 back first (the INSERT in "Rollback" above), because step 6
deleted them.

**Lesson:** a window step done in the browser names the prod URL and gets a read-back in the next paste. A UI delete
leaves no record in any kit's output; this one was caught only by the BA's close check.

### What the integration token can read after RT4 (RT4_RULING_2 Q4)

Exactly the **24 GET routes marked `@integration_readable`**, and nothing else:
- chassis records (9);
- production jobs (7);
- floor state and events (2);
- MES materials (2);
- demand lines, discrepancies and stock counts (1 each);
- one saved costing by id (`GET /api/calculations/{id}`, newly marked in RT4).

Every other route needs a signed-in session; no write accepts the token.

### Open, not RT4's (queued by the BA)

- **The CI snapshot ≠ prod** since the 3–4 Oct hand edits (`all.json` predates them). The README's standing rule asks
  for a refresh with the pruned prod list. The CA recommends RT5.
- **Accepted-list entries that now cover new gaps:** ICECREAM UP TO 4.8, −R259.72, PASS → ACCEPTED.
- **The Burt gap table for the five Mannis** (report only, the input for the next job):
  `docs/audit/rt4_2026-10/burt_gap/MANNI_GAP_TABLE.md`.
- **Already queued:** the duplicate `GET /api/import/sheets`; a role review; the old-stylesheet clean-up; the Trailer
  Designer console error.
