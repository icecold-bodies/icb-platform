# Prod deploy: v1.61.0 (RT6): Burt's insulation rules ENFORCED, the TEST SERVER banner, checked backups, safe pastes

**Status: NOT RUN — committed before the window (RT6_RULING_1 / 1a).** The OUTCOME is appended after the run.
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
| 8 | **Michael's :8000** (after the post-merge procedure's code step, below): `http://127.0.0.1:8000/mes/calculator?stay=1` | the red **TEST SERVER — 127.0.0.1:8000 — not prod** bar, and the tab title starts with **`[TEST]`** |
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

## After the window and the merge: Michael's :8000 (the post-merge procedure)

1. **Code:** the CA fast-forwards the main clone to the merge commit (Michael's local entries fingerprinted before
   and after, never stashed, reset or overwritten), rebuilds the SPA, and gives Michael the dev one-liner: a checked
   backup of `icb`, then `alembic upgrade 0053`. The CA reads it back before :8000 restarts (`start.bat` would
   auto-upgrade). **Window step 8** reads the bar on :8000 after this.
2. **The rules on dev:** `rt6_rules.py --target dev` dry-run ("2 to apply") → Michael applies with `--apply
   --out-dir C:\Users\micge\Documents\icb_db_backups\rt6-dev-rules` → the CA reads it back with `--show`.
3. **Michael's click-through on `http://127.0.0.1:8000`:** the TEST bar; a chiller's PU greyed; a freezer's EPS greyed
   on the sides; the Paste refusal.

## Simulation (WSL; the real `icb-deploy.sh`, the real `mkstage*.sh`)

| kit | scenarios | result |
|---|---|---|
| `ops/prod-release-v1.61.0/sim/run_all.sh` | happy (verify before = exactly 24) · notag · moved · bootfail · traceback · stalecache · resume · migfail · nobackup · pgdumpfail · cfstale · famchanged · nobuild · autologin · noenv · envother · wrongplace | see RT6_RETURN_2 |
| `ops/prod-rt6/sim/run_window_sim.sh` | staging (five kits, the two Windows lines filled) · rules: wrong machine / database / code / alembic, tampered kit, a different plan, a failed dump, dry-run, apply, again, show, revert, revert twice, re-apply · tidy (real files): wrong machine, dry-run, a changed / extra / missing file, apply (owners and modes kept, the stays stay), again, show, restore, never mixed into · All / doors: the first line, wrong machine | 36 / 36 |
| `ops/prod-rt5/sim/run_notes_sim.sh` (rt5_notes.sh on the helper) | as RT5 | 16 / 16 |
| `ops/prod-rt6/rt6_rules.py` on the prod mirror | dry-run 2 → apply → 0 to apply, 2 already applied → show → revert exact → re-applied | see RT6_RETURN_2 |
