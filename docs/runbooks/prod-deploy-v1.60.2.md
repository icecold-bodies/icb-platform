# Prod deploy: v1.60.2 (RT5): Burt's body rules shown in red, in one window

**Status: NOT RUN — committed before the run (RT5_RULING_1); the OUTCOME is appended after it.**
(Before: v1.60.1 = `01751fa`, alembic 0051.) Michael runs every prod step. The CA stages the kits and reads the records
back. **Every browser step names the prod address, and is read back from prod's database in the next paste**
(RT5_RULING_0: RT4's step 6 ran on another server and left no trace).

## What ships

- **Migration 0052:** `trailer_groups.rule_note TEXT NULL`. Guarded and additive; up → down → up and both re-runs were
  proven on `icb_test`, and the upgrade ran on the prod mirror. A backup is taken before it.
- **The family's rule note in red** (`#D12424`, 4.91:1 on `#FFFFFF` and `#F5F7FB`; the skin's own `--red` `#DC2626`
  only reaches 4.50:1):
  - **in the calculator:** directly under **BODY OPTIONS** with a ⚠ icon, on new and re-opened costings; it changes
    with the body (`calculator.js?v=187`);
  - **in Body Templates:** under the body's header (`admin_templates.js?v=22`);
  - **never** on a customer document or an export. The tests compare the report, Word, Excel and PDF with and without
    a note.
- **The family editor** (Admin → Quote templates) gets a **Rule note** column: plain text, several lines allowed,
  500 characters at most. It is admin-only in the API (403 for anyone else) and always shown as text, never as HTML.
- **`/api/trailers`** rows carry `rule_note` beside RT3's `family`, whose ratified shape is unchanged.
- **The INSULATION FOAM picker** (32D / 4G) is **hidden** when the options panel offers no PU choice **and** none is
  selected. This is display only: the foam grade every request sends is unchanged.
- **The freezer audit pack:** `roof_floor_eps` (EPS on the roof and floor, PU elsewhere) replaces `all_eps` in the
  freezers pack and the smoke pack's freezer. Its golden was built from Burt's corrected 21 Sep set the RT2 way.
  The scenario and cell totals do not change.
- **The two notes are DATA**, set after the deploy by `rt5_notes.sh`. **Wording approved by Michael (RT5_RULING_1),
  exactly:**
  - **CHILLER:** `No PU insulation for Chillers`
  - **FREEZER:** `Freezers: EPS insulation in the ROOF and FLOOR only, never in the SIDES, FRONT or doors`
- **Unchanged:** no option, price, formula, rule, draft, BOM row or customer document changes. There is no new
  dependency, no SPA rebuild and no new route: RT4's gate and its 44 probes are unchanged.

## The kits (committed, staged byte-exact from the merge commit)

| kit | staged by | runs |
|---|---|---|
| `icb-release-v1.60.2` | `bash ops/prod-rt5/mkstage_window.sh <out> <merge-sha>` (after the tag) | `release.sh preflight / verify / deploy` |
| `icb-rt5-notes` | the same | `rt5_notes.sh dryrun / apply / show / revert` |
| `icb-rt2-all` | the same (over v1.60.1 **or** v1.60.2; C11 also reads `/var/backups/icb-rt5-2026-10`) | `rt2_all.sh pre / post` |
| `icb-rt2-doors` | the same | `rt2_doors.sh` |

## Sequence

**0. Michael picks the window.** It takes about 40 minutes. The restart means a few seconds of outage.

**1. Merge, tag, stage (after RT5_RULING_2).**
- **Merge:** CI must be green on the PR's exact head. Michael gives the word, and the PR is squash-merged into
  `backport/v1.39-base`. The merge commit is the target, and its tree must equal the CI-tested tree.
- **Tag:** the CA runs `git tag -a v1.60.2 <merge-sha> -m "…"`, then `git push origin v1.60.2`. The CA then proves
  the **tag object** on origin equals the local one, peeled to the merge commit.
- **Stage:** the CA runs `bash ops/prod-rt5/mkstage_window.sh <out> <merge-sha>`.
- **Copy:** Michael copies the kits. From Windows PowerShell:
  - `scp "<out>\icb-release-v1.60.2.tar" "<out>\icb-rt5-notes.tar" "<out>\icb-rt2-all.tar" "<out>\icb-rt2-doors.tar" mickeyger@192.168.0.251:/tmp/`
  - `ssh mickeyger@192.168.0.251 "cd /tmp && tar -xf icb-release-v1.60.2.tar && tar -xf icb-rt5-notes.tar && tar -xf icb-rt2-all.tar && tar -xf icb-rt2-doors.tar"`

**2. Preflight and the known-fail check (read only, any time before the window).** On the VM:

```
sudo bash /tmp/icb-release-v1.60.2/release.sh preflight
sudo bash /tmp/icb-release-v1.60.2/release.sh verify
```

`preflight` asserts:
- db `icb_platform`, alembic 0051, HEAD `01751fa`, no tracked modifications, and no `rule_note` column yet;
- `calculator.js?v=186` and `admin_templates.js?v=21` are loaded, and both doors serve the v1.60.1 blobs;
- the SPA served = disk;
- health 200;
- `/health/version` = **v1.60.1** on all three doors, and RT4's 44 no-session probes all answer as listed;
- PyYAML 6.0.2, and **the `v1.60.2` tag object is on origin**;
- the backup directory is writable, `deploy/prod/icb-deploy.sh` is the expected blob, and icb's sudo is NOPASSWD.

`verify` before the deploy **must fail on exactly 15 checks** (the simulation's list):
- `HEAD`, `TAG_LOCAL`, `DESCRIBE` (v1.60.1 today);
- `ALEMBIC` (0051), `COLUMN` (none);
- `TOOL_IMPORT`: no `RULE_NOTE_INK` yet;
- `VERSION_LOCAL / _LAN / _CF` (v1.60.1);
- `V_calculator` (186), `LOCAL_calculator`, `LAN_calculator`;
- `V_admin_templates` (21), `LOCAL_admin_templates`, `LAN_admin_templates`.

**3. The window** (RT5_RULING_1, in this order).

| # | who | step | pass condition |
|---|---|---|---|
| 1 | Michael | Admin → Costing audit → **All**; when it finishes, `sudo bash /tmp/icb-rt2-all/rt2_all.sh pre` | `PAGE = CLI`. Recorded as the "before"; freezers read **27 / 24 / 522 / 117** (UNVERIFIABLE / ACCEPTED / PASS / SKIP: the old `all_eps`) |
| 2 | Michael | `sudo bash /tmp/icb-release-v1.60.2/release.sh deploy` | `######## DEPLOYED` and every post-deploy assert passes:<ul><li>the backup before 0052;</li><li>alembic **0051 → 0052**;</li><li>`COLUMN` = `rule_note:text:YES:NULL`;</li><li>the families unchanged by the migration and the restart (md5);</li><li>`VERSION_LOCAL/LAN/CF` = **v1.60.2**;</li><li>`NOAUTH_*` "all 44 as expected" on the three doors;</li><li>both scripts' new blobs on both doors;</li><li>the SPA unchanged.</li></ul>"families with a rule note: 0" |
| 3 | Michael | `sudo bash /tmp/icb-rt5-notes/rt5_notes.sh dryrun` → `… apply` → `… show` | dry-run reads **2 to apply, 0 already applied**: CHILLER on its 3 bodies, FREEZER on its 3. Apply writes them in one transaction and keeps the journal + backup in `/var/backups/icb-rt5-2026-10/`. Its own second dry-run reads **0 to apply, 2 already applied**. **`show` = the prod-DB read-back:** CHILLER and FREEZER carry exactly the two approved texts, and every other family `None` |
| 4 | Michael | **All** → `rt2_all.sh post` | `PAGE = CLI`. **No change** on chillers, icecream and explosive against step 1. **Freezers 0 / 24 / 549 / 117**: the 115 `all_eps` cells are replaced by 115 `roof_floor_eps` ones, and the total is still 690. All 2 702 cells (C11: the page run must start after the notes' journal) |
| 5 | Michael | **Browser, on the prod address only:** `https://192.168.0.251/mes/calculator?stay=1` (the LAN door; the address bar must read exactly this) | **CHILLER MEDIUM:** the red note `No PU insulation for Chillers` under BODY OPTIONS, and **no** INSULATION FOAM picker. **FREEZER MEDIUM:** the red freezer note, **and** the picker. **EXPLOSIVE 4.9 AND UP** and **ICECREAM BODY MEDIUM:** no note |
| 6 | Michael | **Admin edit, on the prod address only:** `https://192.168.0.251/admin/quote-templates?skin=mes`. In the **FREEZER** row's Rule note, add ` (TEST)` at the end and click **Save**. Then `sudo bash /tmp/icb-rt5-notes/rt5_notes.sh show`. Then open `https://192.168.0.251/mes/calculator?stay=1` → FREEZER MEDIUM. Then set it back: delete ` (TEST)` → Save. Then `rt5_notes.sh show` **and** `rt5_notes.sh dryrun` | **First `show`:** FREEZER reads the approved text + ` (TEST)`. **The calculator:** shows the same. **Second `show`:** FREEZER reads exactly the approved text again, and the dry-run reads **0 to apply, 2 already applied**. **If either read-back does not match, STOP: the edit went to another server** |
| 7 | Michael | `sudo bash /tmp/icb-rt2-doors/rt2_doors.sh` | **SUMMARY: 14 OK** |
| 8 | Michael | `sudo bash /tmp/icb-release-v1.60.2/release.sh verify` | **0 failed** (the three doors again, after the data) |

`release.sh deploy`, step by step:

| step | what | asserted |
|---|---|---|
| 1 anchors | the start state | **Start states:**<ul><li>**fresh:** HEAD `01751fa` + alembic 0051;</li><li>**resume:** HEAD = target, alembic 0051 or 0052;</li><li>**already deployed:** HEAD = target + 0052 + the completion record. The asserts run; nothing changes.</li></ul>No tracked modifications; rollback anchor written; the families' md5 recorded |
| 2 bytes before | the served baseline | each script's `?v=` and blob on both doors (v1.60.1); SPA served = disk |
| 3 PyYAML | present | 6.0.2 (nothing is installed) |
| 4 **backup** | `pg_dump -Fc` → `/var/backups/postgres/icb_platform_pre-v1.60.2_<ts>.dump` (mode 600): **the rollback for 0052** | size > 0, sha256 printed; `pg_restore --list` has TABLE DATA incl. `alembic_version`, `trailer_groups`, `trailer_types` |
| 5 fetch + guards | `git fetch origin --tags` as icb | **Must hold:**<ul><li>origin = the staged target;</li><li>the tag object, peeled, and `git describe` = `v1.60.2`;</li><li>`01751fa` is an ancestor;</li><li>the changed-file count + C-sorted sha256 = staged.</li></ul>**Must not happen:** any migration other than exactly `0052_trailer_group_rule_note.py`; a dependency change; any change under `frontend/` or `deploy/` |
| 6 dry run | `icb-deploy.sh <target> --dry-run` as icb | "DB migration YES - 0052_trailer_group_rule_note.py", "SPA rebuild no", "Service restart YES" |
| 7 deploy | `icb-deploy.sh <target> --yes`: ff-only, its own backup, `alembic upgrade head`, restart, health | exit 0, "DEPLOYED"; MainPID changed; the completion record |
| 8 post-deploy | after 20 s | **Code and schema:** HEAD, tag, describe; alembic **0052**; the column; families unchanged.<br>**Service:** active; started after the code moved; 4 workers; 0 BOOTSTRAP FAILED; 0 tracebacks; health; PyYAML; the tools import (`roof_floor_eps` + `RULE_NOTE_INK` = `#D12424`).<br>**Doors:** `/health/version` = **v1.60.2** on 127.0.0.1, LAN, Cloudflare; all 44 no-session probes as listed on all three.<br>**Served files:** both scripts' new `?v=` and blobs on both doors; the SPA unchanged |

Everything is logged under:
- `/tmp/icb-release-v1.60.2/out-<mode>-<ts>/`
- `/tmp/icb-rt5-notes/out-<mode>-<ts>/`
- `/tmp/icb-rt2-all/out-<label>-<ts>/`
- `/tmp/icb-rt2-doors/out-<ts>/`

## Behaviour a user can notice

- **Chillers and freezers:** every chiller and freezer quote shows Burt's rule in red under BODY OPTIONS, and so does
  Body Templates for those bodies.
- **The foam picker:** on a chiller the INSULATION FOAM picker is gone, because the panel offers no PU. On a costing
  re-opened with PU on it, the picker shows again. That is RT6's ground: the rules are shown, not yet enforced.
- **The admin:** an admin can change a note in Admin → Quote templates, and the change shows at once. Plain text only.

## Rollback (decided before the run)

**Data first, then code.**

**The notes:** `sudo bash /tmp/icb-rt5-notes/rt5_notes.sh revert /var/backups/icb-rt5-2026-10/journal_notes_<…>.json`.
Both notes go back to empty; the tool refuses if one moved since (an admin edit), and then the note is cleared in the
editor instead.

**The code:** back to `01751fa`:
- `sudo -u icb git -C /opt/icb-platform reset --hard 01751fa`, then `sudo systemctl restart icb-backend`. No SPA build:
  `frontend/` is unchanged in this range.
- The 0052 column may stay. It is nullable and additive, and the v1.60.1 code never reads it. `alembic downgrade` is
  not part of the rollback.
- Then `release.sh verify` from the v1.60.1 kit, or a probe: `/health/version` reads v1.60.1.

**The full restore** (only if both of the above fail): the step-2 dump `icb_platform_pre-v1.60.2_<ts>.dump`.

## After the window and the merge: Michael's :8000 (the post-merge procedure, RT5_RULING_0 Step 0.6)

1. The CA fast-forwards the main clone to the merge commit (local changes kept, fingerprinted), rebuilds the SPA,
   and gives Michael the dev paste: a backup, then `alembic upgrade 0052`. The CA reads it back before restarting
   :8000 (`start.bat` would auto-upgrade).
2. **The dev families step (RT5_RULING_1 Q6).** The CA runs `python ops/dev-rt5/dev_families.py` (read only) and sends
   the plan. Michael applies it with `--apply --expect-plan <sha> --out-dir C:\Users\micge\Documents\icb_db_backups\rt5-dev-families`.
   A `--revert <journal>` undoes it.
3. **The two notes on dev:**
   - **Dry-run:** `python ops/prod-rt5/rt5_notes.py --target dev` reads "2 to apply".
   - **Apply:** `--target dev --apply --out-dir C:\Users\micge\Documents\icb_db_backups\rt5-dev-notes`. Michael runs it.
   - **Read-back:** the CA runs `--target dev --show`.
4. **Michael's click-through on `http://127.0.0.1:8000`:**
   - CHILLER MEDIUM: the note, and no foam picker;
   - FREEZER MEDIUM: the note, and the picker present;
   - an explosive or ice-cream body: no note.

   Dev's drafts still offer the removed choices, so the picker may still show on a dev chiller. Whether to remove
   those choices on dev too is Michael's call (RT5_RULING_1 Q6).

## Simulation (WSL; the real `icb-deploy.sh`, the real `mkstage*.sh`)

| kit | scenarios | result |
|---|---|---|
| `ops/prod-release-v1.60.2/sim/run_all.sh` | happy (verify before = exactly 15) · notag · moved · bootfail · traceback · stalecache · resume · migfail · nobackup · cfstale · famchanged | see `RT5_RETURN_2` |
| `ops/prod-rt5/sim/run_notes_sim.sh` | dryrun · a failed backup (nothing applied) · apply (journal, provenance, backup, second dry-run) · already applied · show · revert · another note · alembic 0051 · tampered kit · code moved | 16 / 16 |
| `ops/prod-rt5/rt5_notes.py` on the prod mirror | dry-run 2 → apply → 0 to apply, 2 already applied → show → revert exact → re-applied | `RT5_RETURN_2` |

## OUTCOME

*(appended after the run)*
