# Prod deploy: v1.61.0 (RT6): Burt's insulation rules ENFORCED, the TEST SERVER banner, checked backups, safe pastes

**Status: RUN 15 Oct 2026, 12:51–13:20 SAST — DEPLOYED; see the OUTCOME at the end.** This runbook was committed
before the run (RT6_RULING_1 / 1a); RT6_RULING_3 amended two pre-deploy expectations; the OUTCOME is appended after it.
(Before: v1.60.2 = `a429404`, alembic 0052, the two rule notes set.) Michael runs every prod step; the CA stages the
kits and reads every record back. **Every paste is a safe one-liner:** its FIRST output line names the machine, the
database (name @ host) and the git HEAD, and the kit refuses a wrong place before anything runs. **Every browser step
names the prod address,** and its effect is read back from prod's database in the next paste.

## What ships

- **Migration 0053:** `trailer_groups.insulation_rule TEXT NULL` — the family's machine-readable rule, canonical
  JSON naming all six panels (`{"allowed": {"FRONT": [...], "SIDES": [...], "ROOF": [...], "FLOOR": [...],
  "DRD": [...], "SRD": [...]}}`). Guarded and additive; up → down → up and both re-runs proven on `icb_test`; upgraded
  on the prod mirror. A checked backup is taken before it.
- **The one check** (`services/insulation_rules.py`, used through `services/rule_guard.py`) — classification by
  mechanism (master `body_option_group` + name token + INSULATION choice group; cost lines by material and the
  condition that gates them), the same code the discovery and `rt6_rules.py` run:
  - **Calculate warns** (`rule_breaches` in the result); it still prices.
  - **Approve refuses (409)** a quote that breaks the family's rule — every save path, every role — with the breach
    named: "Remove it, then save again." Nothing is written.
  - **Accept, the pre-job card and a job from a costing refuse (409)** a saved costing that breaks the **current**
    rule: "Re-open it, Remove, save, then accept." (RULING_1 Q3.) Decline, delete and restore are **not** guarded; a
    saved costing is never altered. Repairs have no family and no guard (Q4).
  - The check lives in the routers, never in the pricing engine or the audit probe.
- **The calculator** (`calculator.js?v=189`):
  - a forbidden choice is **greyed out** with the rule as its tooltip, in all three renderers (Settings draft, flat
    panel, configurator tree); the INSULATION FOAM picker hides when no PU is offered;
  - a re-opened costing that breaks the rule shows a red **"This quote breaks the rule above"** list under the note,
    each line with **Remove**: it clears the forbidden choice and selects the panel's one allowed insulation,
    carrying the thickness (overlay and edit pins) — nothing is written until the user saves (Q2);
  - a forbidden insulation on the door the quote does not use is named "— not used on this quote" (Q8);
  - **Paste from Excel** refuses a forbidden row (red, "refused — <the rule>") and applies the rest;
  - **Switch ALL insulation** skips the forbidden panels and says so.
- **The family editor** (Admin → Quote templates) gets an **Insulation rule** column: an Enforce tick and a 6 × 2
  grid (admin-only, 403 otherwise; every panel needs at least one allowed insulation). Body Templates lists any
  insulation choice the check cannot read (admins). Draft save / backup restore / cross-body restore **warn, never
  block**, when the draft offers a forbidden choice.
- **The TEST SERVER banner** (`ICB_ENVIRONMENT`): every HTML page of a server whose key is not exactly `prod` carries
  a red top bar "TEST SERVER — <host> — not prod" and a `[TEST]` tab title. `/health/version` returns
  `{"version", "environment"}`. The admin dashboard's PROD / DEV badge reads the same key (Q6). Prod gets
  `ICB_ENVIRONMENT=prod` **appended by merge** to `/etc/icb/backend.env` before the restart; Michael's :8000 stays
  unset, so its bar shows.
- **The SPA** (rebuilt by the deploy): Accept shows the 409's sentence ("This costing cannot be accepted. …").
- **Two new admin routes** (`/api/trailers/{id}/insulation-rule-check`, `/api/configurator/draft-snapshots/{id}/
  rule-warnings`): RT4's no-session gate covers them — 46 probes (v1.60.2's 44 + these two, 401).
- **Ops:** `ops/lib/icb_where.sh` (the safe-paste line) and `ops/lib/icb_backup.sh` (the checked backup:
  PIPESTATUS + content check; a CI guard refuses any other `pg_dump` pipe in `ops/`). The six data kits and
  `pc_prod.sh` are **retired** (they refuse to run); `rt5_notes.sh` uses the helper.
- **Burt's two rules are DATA**, set after the deploy by `rt6_rules.sh` (journaled):
  - **CHILLER:** PU allowed nowhere — every panel `["EPS"]`.
  - **FREEZER:** EPS on the ROOF and FLOOR only — FRONT / SIDES / DRD / SRD `["PU"]`, ROOF / FLOOR `["EPS","PU"]`.
  - Every other family: no rule.
- **Unchanged:** no price, formula, option, BOM row, draft, draft backup or saved costing. No dependency. The audit's
  cells cannot move (the check is not in the pricing engine): All after = **No change**.

## The kits (committed, staged byte-exact from the merge commit by ONE script)

`bash ops/prod-rt6/mkstage_window.sh <out> <merge-sha>` (after the tag is on origin) stages all five, each with
`lib/` and the place it must run (`icb-mes-prod`, `icb_platform @ 127.0.0.1:5432`, the HEADs it may see):

| kit | runs | over |
|---|---|---|
| `icb-release-v1.61.0` | `release.sh preflight / verify / env / deploy` | v1.60.2 (and v1.61.0 after the deploy) |
| `icb-rt6-rules` | `rt6_rules.sh dryrun / apply / show / revert <journal>` | v1.61.0 + alembic 0053 only |
| `icb-rt6-tidy` | `rt6_tmp_tidy.sh dryrun / apply / show / restore <archive>` | either |
| `icb-rt2-all` | `rt2_all.sh pre / post` (C11 reads `/var/backups/icb-rt{2,4,5,6}-2026-10`) | either |
| `icb-rt2-doors` | `rt2_doors.sh` | either |

Beside the tars: **`run_window_copy.ps1`** (one line on Windows: checks each tar's sha256, copies, unpacks and
verifies on prod) and **`run_window_fetch.ps1`** (one line: brings every `out-*` folder back to Downloads in one tar).
Both are ASCII, print the identity line first, and refuse a wrong machine or prod HEAD (the VPN must be up).

## Sequence

**0. Michael picks the window.** About 50 minutes; the restart means a few seconds of outage.

**1. Merge, tag, stage (after RT6_RULING_2).**
- **Merge:** CI green on the PR's exact head; Michael gives the word; squash-merge into `backport/v1.39-base`. The
  merge commit is the target; its tree must equal the CI-tested tree.
- **Tag:** `git tag -a v1.61.0 <merge-sha> -m "…"`, `git push origin v1.61.0`; the CA proves the tag object on origin
  = local, peeled to the merge commit.
- **Stage:** `bash ops/prod-rt6/mkstage_window.sh <out> <merge-sha>` → `C:\Users\micge\Documents\icb-rt6-stage\window\`.
- **Copy (Michael, one line, PowerShell or Command Prompt):**
  `powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt6-stage\window\run_window_copy.ps1"`
  → `######## DONE - the five kits are in prod /tmp, verified.`

**2. Preflight (read only, any time before the window).** On the VM:
`sudo bash /tmp/icb-release-v1.61.0/release.sh preflight` → **`PREFLIGHT PASSED`**. It asserts: db `icb_platform`,
alembic 0052, HEAD `a429404`, no tracked modifications, no `insulation_rule` column yet; **`MES_DEMO_AUTOLOGIN_USER
empty: yes`** (only yes/no is ever printed); `ICB_ENVIRONMENT` absent (or already `prod`); the three statics at
v1.60.2 (`calculator.js?v=187`, `admin_templates.js?v=22`, `app.js?v=6`) on both doors; SPA served = disk, without the
refusal sentence yet; health 200; `/health/version` = v1.60.2 on the three doors; all 46 no-session probes as listed on
the three doors; PyYAML 6.0.2; npm + `node_modules` present; **the `v1.61.0` tag object on origin**; the backup
directory writable; `deploy/prod/icb-deploy.sh` the expected blob; icb's sudo NOPASSWD.

**3. The window** (RULING_1 + 1a, in this order; every line is one paste on the VM unless it says browser).

| # | step | pass condition |
|---|---|---|
| 1 | Admin → Costing audit → **All**; when it finishes: `sudo bash /tmp/icb-rt2-all/rt2_all.sh pre` | first line `######## RT6 All pre (read only) · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head a429404`; **PAGE = CLI**. Recorded as "before" |
| 2 | `sudo bash /tmp/icb-release-v1.61.0/release.sh verify` (verify-before) | **`MES_DEMO_AUTOLOGIN_USER` `PASS AUTOLOGIN_EMPTY = yes`** — if it reads **no: STOP, do not deploy, tell the BA.** `VERIFY` fails on **exactly the 24 not-yet-deployed checks** (below) and nothing else |
| 3 | `sudo bash /tmp/icb-release-v1.61.0/release.sh env` | `before: absent` → `read back: ICB_ENVIRONMENT=prod`; "every earlier line byte-identical; root:… 600 kept"; a copy of the file kept in `/var/backups/icb-rt6-2026-10/`. **Only that one line is added**; the duplicate keys are not touched |
| 4 | `sudo bash /tmp/icb-release-v1.61.0/release.sh deploy` | **`######## DEPLOYED`**: autologin empty; the env key present; the **checked** backup (`pg_restore -l` lists the TABLE DATA of `alembic_version`, `trailer_groups`, `trailer_types`, `calculations`, `bill_of_materials`); 0052 → **0053**; the column = `insulation_rule:text:YES:NULL`; the families unchanged (md5); SPA rebuilt and carrying the refusal; 4 workers, 0 BOOTSTRAP FAILED, 0 tracebacks; **`/health/version` = `{"version":"v1.61.0","environment":"prod"}` on 127.0.0.1, then LAN, then Cloudflare**; **no TEST banner** on any door (`0/0`); all 46 probes as listed on the three; the three statics' new `?v=` and blobs on both doors |
| 5 | `sudo bash /tmp/icb-rt6-rules/rt6_rules.sh dryrun` → `… apply` → `… show` | dry-run **2 to apply, 0 already applied** (CHILLER on its 3 bodies, FREEZER on its 3). Apply: a checked data-only backup of `trailer_groups`, one transaction, journal + provenance in `/var/backups/icb-rt6-2026-10/`; its second dry-run **0 to apply, 2 already applied**. **`show`:** CHILLER and FREEZER carry exactly the planned rules, every other family `None`; per ruled body the greyed masters |
| 6 | **All** → `sudo bash /tmp/icb-rt2-all/rt2_all.sh post` | **PAGE = CLI; No change** against step 1 on all five packs; **0 FLAG** (C11: the page run must start after the rules' journal) |
| 7a | **Browser, at the prod address only:** `https://192.168.0.251/mes/calculator?stay=1` (the address bar must read exactly this) | **No** TEST SERVER bar, **no** `[TEST]` in the tab title |
| 7b | the same page → **new** quote → body **CHILLER MEDIUM** | every PU choice on the panel (FRONT / SIDES / ROOF / FLOOR, and the door the quote uses) **greyed out**, its tooltip the rule; no INSULATION FOAM picker. **Do not save** |
| 7c | the same quote → **Paste from Excel** → paste one row copied from Excel: `FRONT PU` · `Y` · `0.06` (three cells) | the preview shows the row in red: **"refused — No PU insulation for Chillers"**. Close the dialog. **Calculate only — never approve, never save** |
| 7d | `sudo bash /tmp/icb-rt6-rules/rt6_rules.sh show` (the read-only breach count, RULING_1a) | **`live breaching costings: 0`**; **`soft-deleted breaching costings: 1`** (A9998/09/2026, quote number only). No costing was created by 7b / 7c |
| 8 | **Michael's :8000** (the post-merge procedure ran before the window, below): `http://127.0.0.1:8000/mes/calculator?stay=1` | the red **TEST SERVER — 127.0.0.1:8000 — not prod** bar, and the tab title starts with **`[TEST]`** |
| 9 | `sudo bash /tmp/icb-rt6-tidy/rt6_tmp_tidy.sh dryrun` → `… apply` | dry-run: **34 of 34 present, all 47 files match** the reviewed sha256s. Apply: the 34 move (never a glob, never a delete) to **`/var/backups/icb-tmp-archive-<date>/`** (root:root 700) with `LISTING.txt` and `SHA256SUMS`; **read back:** the archive's sums = the reviewed list, none of the 34 left in /tmp, `node-compile-cache/` still there. RT6's kits and the deploy's own new rollback note stay |
| 10 | `sudo bash /tmp/icb-rt2-doors/rt2_doors.sh` | **SUMMARY: 14 OK** |
| 11 | `sudo bash /tmp/icb-release-v1.61.0/release.sh verify` | **0 failed** (the three doors again, after the data); families with an insulation rule: **2** |
| 12 | Windows, one line: `powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt6-stage\window\run_window_fetch.ps1"` | `######## DONE - tell the CA: …\Downloads\rt6-window-back-<ts>.tar` |

**Verify-before must fail on exactly these 24** (the simulation's list): `HEAD`, `TAG_LOCAL`, `DESCRIBE`, `ALEMBIC`
(0052), `COLUMN` (none), `ENV_KEY` (absent), `TOOL_IMPORT`, `VERSION_LOCAL / _LAN / _CF` (v1.60.2), `ENVIRONMENT_LOCAL /
_LAN / _CF` (none today), `V_calculator` (187), `LOCAL_calculator`, `LAN_calculator`, `V_admin_templates` (22),
`LOCAL_admin_templates`, `LAN_admin_templates`, `V_app` (6), `LOCAL_app`, `LAN_app`, `SPA_HAS_REFUSAL_LOCAL / _LAN`.
Everything else passes — **`AUTOLOGIN_EMPTY = yes` above all.**

**The re-open → warning → Remove → Accept-refused proof is NOT a prod step** (RULING_1a: no test quote on prod). It
comes from the prod-mirror rehearsal and the side-port journey (`docs/audit/rt6_2026-10/`, RT6_RETURN_2).

`release.sh deploy`, step by step:

| step | what | asserted |
|---|---|---|
| 1 anchors | the start state | **fresh:** HEAD `a429404` + alembic 0052; **resume:** HEAD = target, alembic 0052 or 0053; **already deployed:** HEAD = target + 0053 + the completion record (the asserts run; nothing changes). No tracked modifications; rollback anchor written; the families' md5 recorded |
| 2 autologin + env | before anything moves | `MES_DEMO_AUTOLOGIN_USER` empty (else STOP); `ICB_ENVIRONMENT=prod` in the file (else STOP: "run `release.sh env` first") |
| 3 bytes before | the served baseline | the three statics' `?v=` and blobs on both doors (v1.60.2); SPA served = disk |
| 4 PyYAML | present | 6.0.2 (nothing is installed) |
| 5 **backup** | `icb_backup … custom` → `/var/backups/postgres/icb_platform_pre-v1.61.0_<ts>.dump`: **the rollback for 0053** | `pg_dump` exit 0; size > 0; `pg_restore -l` lists the five tables' DATA; sha256 printed |
| 6 fetch + guards | `git fetch origin --tags` as icb | origin = the staged target; the tag object, peeled, and `git describe` = `v1.61.0`; `a429404` an ancestor; the changed-file count + C-sorted sha256 = staged; exactly one migration (`0053_trailer_group_insulation_rule.py`); no dependency change; `deploy/` untouched; `frontend/` changed (the SPA rebuild) |
| 7 dry run | `icb-deploy.sh <target> --dry-run` as icb | "DB migration YES", "SPA rebuild YES", "Service restart YES" |
| 8 deploy | `icb-deploy.sh <target> --yes`: ff-only, its own backup, `alembic upgrade head`, `npm run build`, restart, health | exit 0; MainPID changed; the completion record |
| 9 post-deploy | after 20 s | the `verify` list: code, tag, describe, 0053, the column, the families unchanged, `ENV_KEY`, `AUTOLOGIN_EMPTY`, service (active, restarted after the code moved, 4 workers, 0 bootstrap failures, 0 tracebacks), health, PyYAML, `TOOL_IMPORT` = `6 True`, the three doors (version + environment + no banner), 46 probes × 3, the statics, the SPA |

Records: `/tmp/icb-release-v1.61.0/out-<mode>-<ts>/`, `/tmp/icb-rt6-rules/out-<mode>-<ts>/`,
`/tmp/icb-rt6-tidy/out-<mode>-<ts>/`, `/tmp/icb-rt2-all/out-<label>-<ts>/`, `/tmp/icb-rt2-doors/out-<ts>/`; kept data:
`/var/backups/icb-rt6-2026-10/` (env copy, rules backups, journals, provenance), `/var/backups/postgres/` (the dump),
`/var/backups/icb-tmp-archive-<date>/`.

## Behaviour a user can notice

- **A chiller quote:** every PU choice is greyed out with the rule as its tooltip; pasting a PU row is refused.
- **A freezer quote:** EPS is greyed on the FRONT, SIDES and doors; the roof and floor offer both.
- **A saved costing that breaks the rule** (none live on prod today): re-opened, it shows the red list with Remove;
  it cannot be saved, accepted or sent to the floor until each breach is removed.
- **Admins:** the family editor's Insulation rule grid; a draft that still offers a forbidden choice saves with a
  warning.
- **Prod:** no bar. **Every other server** (Michael's :8000, the mirror, side ports): the red TEST SERVER bar and the
  `[TEST]` title. The admin dashboard badge reads PROD on prod.

## Rollback (decided before the run)

**Data first, then code.**

- **The rules:** `sudo bash /tmp/icb-rt6-rules/rt6_rules.sh revert /var/backups/icb-rt6-2026-10/journal_rules_<…>.json`
  — a checked backup first; both rules back to empty; refuses if a row moved since (an admin edit: then untick
  Enforce in the editor instead). With no rule, nothing is enforced.
- **The /tmp tidy:** `sudo bash /tmp/icb-rt6-tidy/rt6_tmp_tidy.sh restore /var/backups/icb-tmp-archive-<date>`.
- **The code:** back to `a429404`: `sudo -u icb git -C /opt/icb-platform reset --hard a429404`, then the SPA:
  `sudo -u icb bash -lc 'cd /opt/icb-platform/frontend && npm run build'` (frontend/ changed in this range), then
  `sudo systemctl restart icb-backend`; then the v1.60.2 kit's `release.sh verify`, or `/health/version` = v1.60.2.
  The 0053 column stays (nullable, additive; v1.60.2 never reads it). `ICB_ENVIRONMENT=prod` stays (v1.60.2 never
  reads it). `alembic downgrade` is not part of the rollback.
- **The full restore** (only if all of the above fail): `icb_platform_pre-v1.61.0_<ts>.dump`.

## Before the window, after the merge: Michael's :8000 (the post-merge procedure, RT6_DISPATCH)

1. **Code:** the CA fast-forwards the main clone to the merge commit (Michael's local entries fingerprinted before
   and after, never stashed, reset or overwritten) and rebuilds the SPA. Michael runs the dev one-liner (its first
   line names the machine, `icb @ localhost:5432` and the HEAD): a checked backup of `icb`, then `alembic upgrade
   0053`. The CA reads it back before :8000 restarts (`start.bat` would auto-upgrade).
2. **The rules on dev:** `rt6_rules.py --target dev` (run from the main clone; it uses the repo's own check):
   dry-run ("2 to apply") → Michael applies with `--apply --out-dir
   C:\Users\micge\Documents\icb_db_backups\rt6-dev-rules` → `--show` reads them back, and lists dev's breaching
   costings by quote number (one of them is the click-through's re-open).
3. **Michael's click-through on `http://127.0.0.1:8000`** (dispatch): the TEST SERVER bar and the `[TEST]` title; a
   chiller with PU greyed (dev's drafts still offer it); a refused approve; re-open → Remove → approve.

**Window step 8** re-reads the bar on :8000. After the window: nothing more on :8000 (`RT6_RETURN_4`).

## Simulation (WSL; the real `icb-deploy.sh`, the real `mkstage*.sh`)

| kit | scenarios | result |
|---|---|---|
| `ops/prod-release-v1.61.0/sim/run_all.sh` | happy (verify before = exactly 24) · notag · moved · bootfail · traceback · stalecache · resume · migfail · nobackup · pgdumpfail · cfstale · famchanged · nobuild · autologin · noenv · envother · wrongplace | 17 / 17 |
| `ops/prod-rt6/sim/run_window_sim.sh` | staging (five kits, the two Windows lines filled) · rules: wrong machine / database / code / alembic, tampered kit, a different plan, a failed dump, dry-run, apply, again, show, revert, revert twice, re-apply · tidy (real files): wrong machine, dry-run, a changed / extra / missing file, apply (owners and modes kept, the stays stay), again, show, restore, never mixed into · All / doors: the first line, wrong machine | 36 / 36 |
| `ops/prod-rt5/sim/run_notes_sim.sh` (rt5_notes.sh on the helper) | as RT5 | 16 / 16 |
| `ops/prod-rt6/rt6_rules.py` on the prod mirror | dry-run 2 → apply → 0 to apply, 2 already applied → show → revert → revert twice refused → re-applied; RULING_1a on a mirror test costing; All before / after: No change | `docs/audit/rt6_2026-10/mirror/REHEARSAL_v1.61.0.md` |

## OUTCOME

**PROD = v1.61.0 = `5e37b0a`** (#218, squash of `c1030ba`, same tree `81a8d19`; CI green on `c1030ba`):
- **tag:** `v1.61.0` = tag object `d084f7b`; local = origin; peels to `5e37b0a`; `git describe` = v1.61.0;
- **schema:** alembic **0053**; `insulation_rule:text:YES:NULL`; the families unchanged by the migration and the
  restart (md5 `6f1dfa66…` before = after);
- **deployed:** 15 Oct 2026 13:00:35–13:02:03 SAST by Michael's `release.sh deploy`; service restart 13:01:18 (pid
  1098 → 34561), after the code moved; **4 workers**, 0 bootstrap failures, 0 tracebacks; health 200;
- **restore point:** `/var/backups/postgres/icb_platform_pre-v1.61.0_20261015-130035.dump`, **3 608 614 bytes**, sha256
  `e52a8f79a02ed0fdeb6ecb5e2856778f653e18fe84e54b14989392f40611a2c1` (checked: the TABLE DATA of `alembic_version`,
  `trailer_groups`, `trailer_types`, `calculations`, `bill_of_materials`). `icb-deploy.sh`'s own backup:
  `icb_platform_20261015-1300.dump.gz` (3 302 221 bytes);
- **the three doors**, in order 127.0.0.1 → LAN → Cloudflare: `{"version":"v1.61.0","environment":"prod"}`; no TEST bar
  (`0/0`); **all 46 no-session probes as listed**, and the two new routes read back **401** on each door (step 4b);
- **served bytes** (local = LAN = the target blobs): `calculator.js?v=189` `aa99a811ad807dab…`,
  `admin_templates.js?v=23` `ad5d8d480876a20f…`, `app.js?v=7` `c202dbc4fdd043f4…`; SPA `index-Bd_exvgd.js` →
  **`index-BBI2d9Oo.js`** (`cd39cb56c575…`, carries the Accept refusal);
- **environment:** `ICB_ENVIRONMENT=prod` appended to `/etc/icb/backend.env` by merge (34 → 35 lines, every earlier
  line byte-identical, `root:icb 600` kept; copy `/var/backups/icb-rt6-2026-10/backend.env.pre-v1.61.0.20261015-125957`);
  `MES_DEMO_AUTOLOGIN_USER` empty: yes;
- **Burt's two rules ON** (journal `journal_rules_rt6_rules_journal_prod_20261015T110727Z.json`, sha256 `fcaf74ed…`;
  backup `pre_apply_rules_20261015T110726Z.sql.gz`, 868 bytes, sha256 `b1977805…`; both in
  `/var/backups/icb-rt6-2026-10/`). **`show`:** #5 CHILLER
  `{"allowed":{"FRONT":["EPS"],"SIDES":["EPS"],"ROOF":["EPS"],"FLOOR":["EPS"],"DRD":["EPS"],"SRD":["EPS"]}}` (6 PU
  masters greyed on each of its 3 bodies); #4 FREEZER
  `{"allowed":{"FRONT":["PU"],"SIDES":["PU"],"ROOF":["EPS","PU"],"FLOOR":["EPS","PU"],"DRD":["PU"],"SRD":["PU"]}}`
  (DRD / FRONT / SIDES / SRD EPS greyed on each of its 3); EXPLOSIVE, MEAT, ICE CREAM, OTHER `None`.
  **live breaching costings: 0; soft-deleted: 1 (A9998/09/2026)**.

**Nothing priced moved:** All before (page run #44) and after the rules (#45): PAGE = CLI, 2 702 / 2 702; the report
JSONs compared value by value — **0 differences over 104 966 values, 2 936 cells** (`cells_window.txt`).

The evidence is under `docs/audit/rt6_2026-10/prod/window_20261015/` (the fetched tar
`rt6-window-back-20261015-131720.tar`, sha256 `2522f967…`; the pasted one-liners in `window_pastes.txt`).

| # | time (SAST) | step | result |
|---|---|---|---|
| — | 14 Oct 16:46 | copy (`run_window_copy.ps1`) | 5 kits sha-checked, unpacked and verified on prod |
| — | 14 Oct 16:47 / 16:49 | `preflight` / `verify` (read only) | **STOPPED**: 3 FAILED / 27 failed — the two new routes answered **404** (below). `RT6_RETURN_3` → **`RT6_RULING_3` = A** |
| 0 | 15 Oct 12:51 | `preflight` (re-run; also 12:49) | exactly the ruled **3 FAILED**: `NOAUTH_LOCAL / _LAN / _CF` = `'/api/trailers/27/insulation-rule-check=404/401 /api/configurator/draft-snapshots/1/rule-warnings=404/401'`; everything else PASS; autologin empty: yes; tag on origin `d084f7b` |
| 1 | 12:55–12:56 | All (page run #44) → `rt2_all.sh pre` | **PAGE = CLI**, 2 702 / 2 702 — with **156 FLAG** already there (below). (12:55:27: `[PAGE]` stop — the newest page run then was 6 Oct's) |
| 2 | 12:58 | `verify` before | exactly the ruled **27**: the 24 + the three `NOAUTH_*` lines word for word; `AUTOLOGIN_EMPTY = yes`; `TRACEBACKS = 0` |
| 3 | 12:59 | `release.sh env` | `absent` → **`ICB_ENVIRONMENT=prod`**, read back; earlier lines byte-identical |
| 4 | 13:00–13:02 | `release.sh deploy` | **`######## DEPLOYED`** (above) |
| 4b | 13:04 | the two new routes, no session, each door | **401 × 6** (127.0.0.1, LAN, Cloudflare) |
| 5 | 13:06–13:07 | `rt6_rules.sh dryrun` → `apply` (its read-back = `show`) | **2 to apply** → `APPLIED 2 rule(s): #5 CHILLER; #4 FREEZER` → **0 to apply, 2 already applied** |
| 6 | 13:07–13:09 | All (#45) → `rt2_all.sh post` | **PAGE = CLI**, 2 702 / 2 702; **no change** against step 1, cell for cell (the same 156 FLAG — Michael's ruling at step 1). (13:07:58: `[PAGE]` stop, by design: #44 predated the rules' journal) |
| 7a–c | ~13:12 | browser at `https://192.168.0.251/mes/calculator` | **no** TEST bar; tab "Calculator — IceCold"; sidebar v1.61.0. CHILLER MEDIUM: the red note, **EPS only** — prod's drafts offer no PU at all (6 Oct discovery: 0 forbidden choices offered), so nothing is there to grey; the greying itself was proven on :8000 and in the journey (`step7b_prod_chiller_medium_config.png`). The PU paste refused. **Nothing saved** |
| 7d | 13:13 | `rt6_rules.sh show` | **live breaching 0, soft-deleted 1** (A9998/09/2026) |
| 8 | 13:13 | :8000 | `{"version":"v1.61.0","environment":"unset"}`; the bar "TEST SERVER — 127.0.0.1:8000 — not prod"; `[TEST]` title |
| 9 | 13:14–13:15 | the /tmp tidy | **dry-run STOPPED [STATE]: 0 of 34 present** — superseded by the OS (below); **no write** (Michael: skip 9) |
| 10 | 13:16 | `rt2_doors.sh` | **SUMMARY: 14 OK; no exceptions** |
| 11 | 13:16 | `release.sh verify` | **0 check(s) failed**; families with an insulation rule: **2** |
| 12 | 13:17 | `run_window_fetch.ps1` | `rt6-window-back-20261015-131720.tar`, 26 265 600 bytes, sha256 `2522f967…` |
| close | 13:20 | RT6's kits out of prod /tmp, by exact name | **12 × `gone:`** (the five kits + tars; `icb-rt6-discovery/` + tar already gone); kept: the deploy's `icb-rollback-20261015-130040.txt`, `node-compile-cache/` |

**The pre-deploy stop (RT6_RETURN_3 → RT6_RULING_3 = A).** The kit's preflight and verify-before checked the NEW
release's 46-probe list against the OLD code: RT6's two routes (`/api/trailers/{id}/insulation-rule-check`,
`/api/configurator/draft-snapshots/{id}/rule-warnings`) do not exist in v1.60.2 (`git grep`: 0 files of `a429404`), so
the gate answered 404 where the list says 401. Nothing was exposed; the deploy's own steps 1–8 never probe, and after
the code moved every path answered as listed. Ruled: no code change, no re-tag; the two expectations made exact. The
release sim had missed it: its fake doors answered every listed path as listed, whatever code ran. **Fixed in the
OUTCOME PR** (the v1.61.0 tag and the copy that ran stay as they are): `mkstage.sh` derives `NEW_PROBES` from the code
and `release.sh` lets only those answer 404 while prod still runs the old code; the sim's fake doors answer 404 for a
route the running code lacks. Negative control: with the tag's `release.sh` (the copy the window ran) the fixed sim
reproduces the window's 3 preflight FAILs and verify-before 27 word for word (scenario `oldkit`); with the fixed kit,
preflight passes and verify-before is 24; an OLD gated route answering 404 before the deploy still fails
(`oldroute404`). A sim whose fake server cannot fail proves nothing.

**The 156 FLAG cells (accepted by Michael at step 1; for the BA and RT7).** RT5's window ended on 6 Oct at FLAG 0
(page: PASS 2 083 · ACCEPTED 67); on 15 Oct, before anything moved, PASS 1 942 · ACCEPTED 52 · **FLAG 156** (183 with
smoke). No data kit has written prod since 6 Oct 07:22, so prices were edited by hand between 6 and 15 Oct. The cells
sit in the FLOOR sections of the chiller, freezer and ice-cream bodies, FREEZER MEDIUM's DRD DOOR FITTINGS (a constant
−293.46) and ROOF, and ICECREAM BODY MEDIUM's FLOOR (≈ −2 000). Step 6 was judged as no change against step 1, cell for
cell — RT6's rules moved none of them. Not RT6's to change; the CI snapshot refresh (RT7) owns it.

**Step 9 — superseded by the OS (Michael: skip 9; for the BA to ratify).** Prod **rebooted Sun 11 Oct 08:02:53** onto
kernel 6.8.0-146 (the service's previous start, pid 1098). Ubuntu's `D /tmp 1777 root root 30d` empties `/tmp` at boot:
the 34 reviewed items and RT6's own discovery kit were already gone; the tidy's dry-run refused (`0 of 34 present`) and
moved nothing; no archive exists. The end state the tidy was for holds — none of the 34 in /tmp, `node-compile-cache/`
kept — but the files were deleted by the boot, not archived. Their names and sha256s are in
`docs/audit/rt6_2026-10/prod/discovery_20261006-161235/tmp_listing.txt` (old one-off kit scripts and outputs; RT5's
rollback note held only `a429404`, recorded in RT5's OUTCOME). Every prod reboot empties /tmp: a kit staged there must
be re-copied after one.

**Known and accepted: MEAT HANGER SMALL-MEDIUM #36, line #6228** — "#6228 stale option_id, name correct, no pricing
effect" (RT6_RULING_2 §6). Its condition `[{"option": "FLOOR EPS", "equals": "Y", "option_id": 6284}]` names FLOOR EPS
(correct) but carries the FRONT EPS master's id (FLOOR EPS is 6294); the engine matches conditions by name only, so it
prices as intended. The classifier's warning about it is expected. No data change; if the id is ever touched, it goes
with the rule-editor work.

**Also seen, not changed:** `git fetch --tags` on prod printed `! [rejected] v1.47.1 -> v1.47.1 (would clobber existing
tag)` — prod's own copy of that old tag differs from origin's; it does not touch this release.

**Michael's :8000 (before the window, RT6_RULING_2):** main clone fast-forwarded `f441e7a` → `5e37b0a` (the 235 local
entries byte-identical before and after); SPA rebuilt (`index-BBI2d9Oo.js`); dev backup
`icb_db_backups\icb_pre_0053_20261014-163333.dump` (1 844 468 bytes, sha256 `2bdfe46d…`) → 0053; the rules on dev
(journal `rt6-dev-rules\rt6_rules_journal_dev_20261014T143505Z.json`, sha256 `27e79b3f…`); `/health/version` =
`{"version":"v1.61.0","environment":"unset"}`; **Michael's click-through 4/4** (the bar and `[TEST]`; a chiller's PU
greyed; an approve refused; re-open → Remove → approve).
