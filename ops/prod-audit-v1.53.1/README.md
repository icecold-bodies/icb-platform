# WO — v1.53.1 PROD AUDIT: master-bound draft-flag shadowing (read-only)

**Status:** DRAFT for BA-coordinator / Michael. Kit dev-tested 14 Sep 2026 against dev `icb` (read-only) with the same app code prod runs.
**Lane:** follow-up to PR #186 (`94ed70b`, v1.53.1), which is merged and live on dev :8000.

## 1. Why this exists

PR #181 (`e5c7837`, 8 Sep) sent every Explorer draft-flag name to the calculator as an explicit `0` in `body_variable_overrides`. Master-bound v2 bodies (the FREEZER 2.3 METER class) name their flags after their master body-variable rows. As a result:

- the zeros overwrote the real insulation thicknesses on every calc;
- a saved quote could carry `body_variables[SIDES PU] = 0` while the template said 0.062;
- on dev tid 19 at default dimensions this moved total cost by about R 1 800 (**over**-priced).

The direction of the error depends on the body and its dimensions: the insulation lines drop to 0, but the skin/panel deductions shrink as well.

**Prod was exposed without a recorded deploy:**

| When (SAST) | What happened on prod | Effect |
|---|---|---|
| 7 Sep 16:42 | `e9dd6da` deployed (#176–#178 draft-flag thickness) | Narrow shadow window opened: only user-set values on stale-bound flags |
| 8 Sep 09:35 | `/opt/icb-platform` checked out at `e5c7837` (+ restart) to get the prod41 Manni migration tool | #181 explicit-zero JS **served** |
| 8–9 Sep | Checkouts moved to `6621762`, then `04b332f` (tools only) | Served JS stayed at `e5c7837` |
| now | Prod is on a detached HEAD at `04b332f` | Still serving the shadowing JS under `?v=178`; no #184, no #186 |

StaticFiles serves `calculator.js` straight from the checkout, so any `git checkout` on prod is a JS deploy.

## 2. Scope and safety — the audit writes nothing on prod

- **Database:** read by the app's own code with its `DATABASE_URL`. The script contains **no data-modifying statement**, and read-only is enforced in two independent layers:
  - `PGOPTIONS=-c default_transaction_read_only=on`, set before any connection opens;
  - every pooled connection runs `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`, committed so that no rollback can undo it, and then asserts `default_transaction_read_only = on`.
  - Section A aborts the run unless both `transaction_read_only` and `default_transaction_read_only` are `on`. The only COMMITs end those connection-setup `SET`s; every audit transaction is rolled back.
- **Code-state probes:** `git rev-parse/log/merge-base/cat-file`, `grep`/`sha256sum` on `calculator.js`, `curl` GETs of the served bundle and `/openapi.json`, `systemctl show`.
- **Files written:** only `~/icb-prod-audit-v1531/` on the VM (the kit, `out-<run>/`, `out-latest/`, `LAST_RUN`) and `ops/prod-audit-v1.53.1/out/<run>/` on this PC. Git probes run with `--no-optional-locks`, so they don't write the index; Python runs with `-B`, so it writes no `__pycache__`.
- **sudo** is used only to read the root-only `/etc/icb/backend.env` for the Python step, and to `chown` its output back to you.
- **No restart**, no checkout, no service change, no data change.

## 3. How to run (Michael)

From this folder on the Windows PC (`C:\Users\micge\Documents\icb-platform-prod-audit\ops\prod-audit-v1.53.1`), run the command below. Use `-User <your ssh user>` if you don't log in as `icb`.

```powershell
powershell -ExecutionPolicy Bypass -File .\run-prod-audit.ps1
```

You'll get **three SSH password prompts** (copy kit, run audit, fetch results), plus your **sudo password** on the VM if your account asks for one. The launcher:

1. copies an LF-normalised kit to `~/icb-prod-audit-v1531/`;
2. runs `bash ~/icb-prod-audit-v1531/audit.sh <run-id>` over `ssh -t`, so the summary prints live;
3. fetches `out-latest/` into `.\out\<run-id>\`, and **only calls the results fresh if their `RUN_ID` matches this run**. A failed or dropped run can't hand back an older run's results: `audit.sh` deletes `out-latest` first and republishes on every exit path. If ssh fails to log in (exit 255), nothing is fetched.

`-DryRun` stages the kit and prints the three commands without contacting the VM.

**Launcher messages:**
- **Green "Done. Fresh, complete results"** — usable. Tell Claude "prod audit done".
- **"ssh failed (exit 255)"** — login or connection failed; nothing was fetched. Rerun.
- **"NOT from this run (RUN_ID does not match)"** — don't use the folder.
- **"audit exited N ... NOT usable"** — fetched, but incomplete (e.g. sudo failed or the session was not read-only). Read `00_code_state.txt` / `report.txt`.
- **VM banner** — ends with `=== AUDIT COMPLETE ... exit=0 ===`, or `=== AUDIT INCOMPLETE ... ===` on any failure or Ctrl-C.

Then tell Claude **"prod audit done"**. It reads `.\out\<stamp>\` directly, so there's nothing to paste.

**Manual alternative, already on the VM:** copy the `kit/` files (LF line endings) to `~/icb-prod-audit-v1531/` and run `bash ~/icb-prod-audit-v1531/audit.sh`. Results land in `~/icb-prod-audit-v1531/out-latest/`; paste `SUMMARY.txt` back.

Runtime is roughly 1–3 minutes, depending on how many costings sit on the exposed trailers.

## 4. What it checks (output files)

| § | File | Question answered |
|---|---|---|
| 0 | `00_code_state.txt` | Which SHA is prod on? Which bundle do browsers actually get (markers + sha256 on disk and served)? When did the service start? |
| A | `report.txt` | Is the session read-only? DB, timezone, alembic |
| B | `B_exposure_census.csv`, `B_flags.csv` | Per trailer with a draft: flags named after a master body variable; which are wired into a formula; binding state (live / unbound / foreign / missing); whether a stale binding heals by name (1 match, ambiguous, or none); whitespace drift; `flagVarDefault` usage. **Prod trailer ids are NOT dev's — the dev list (22 / 16 v2) does not transfer.** |
| C | `C_pairs_both_gt0.csv` | EPS/PU pair invariant (both sides > 0) on exposed trailers |
| D | `D_costings_in_scope.csv` | Every saved costing on an exposed trailer, compared per master name. One side is the value the **engine actually used**: saved `result_json.body_variables`, read with key order preserved and names normalised the engine's way (`strip().upper()`, last key wins), which catches whitespace/case split keys. The other side is `input_state.ui_snapshot.body_variables[id]`, the template the page had at save time. For duplicate-named masters the template is the one the engine used: the **last** master in the approve path's order (`sort_order`, then section order / section / material name). Disagreeing duplicates are also counted, as information only. See the classification below this table. It also flags a costing when it was created or accepted since the window, or saved by a v1.53 client (`draft_flag_vars` key) whatever its date — which catches in-place edits of older quotes, since `calculations` has no `updated_at`. |
| E | `E_validated_references.csv` | Validated references created in the window, or pointing at a flagged costing (their fingerprints change after the fix) |
| F | `F_impact.csv` | For **SHADOW** costings only (in-window first; any cap is noted in SUMMARY): the approve-path engine re-run twice against **current** prices, with overrides built from the costing's own saved `body_variables`. **shadow** = exactly as saved; **corrected** = the shadowed names set back to their template values (drift names stay as saved). `delta_net` isolates the shadow; `saved_vs_replay_drift` is later price drift plus inputs a replay can't reproduce (`formula_overrides` aren't stored). |
| G | `report.txt` | Readiness for deploying 94ed70b: v2 bodies whose stale bindings will render differently after the heal; ambiguous heals; whitespace drift; `flagVarDefault` on master names; Manni trailers' master/token counts |

**Classification used in D (per name, then per costing):**
- A name is a **shadow** when all of these hold:
  - the save came from a v1.53 client (the snapshot has `draft_flag_vars`);
  - the name is a master-named draft flag that some formula on the trailer references (only those names were ever sent);
  - the saved value is 0 (the #181 explicit zero), or equals that flag's `draft_flag_vars` value (a typed thickness in the #178/#181 era);
  - it differs from the template.
- Any other mismatch is **drift**: the older edit-pin / pair-swap class.
- Costing patterns: **`SHADOW`**, **`SHADOW+DRIFT`**, **`PIN_DRIFT`** (drift only, informational), or empty.
- **`NO_SNAPSHOT_POSSIBLE_SHADOW`** — the costing has no `ui_snapshot` (edit-replay re-saves store none), so there is no save-time template to compare. It's listed when a shadowable name was used at 0 while **today's** template is > 0. Treat it as a manual look: it may be a legitimate unselected side whose template changed later. Never recomputed.

**Dev dry run (14 Sep):**
- 22 exposed trailers (16 v2), 0 pair violations, 0 costings in the window, **0 SHADOW**.
- 2 `PIN_DRIFT` (calcs 1630 and 1642, July — pre-v1.53).
- G all clear.
- Detection logic separately proven on a synthetic `icb_test` fixture, **51/51 checks**, covering:
  - plain #181 zero (delta R 12.28), whitespace split key (R 2.00), #178 typed value (R 4.36);
  - pin drift, shadow+drift, and a clean costing;
  - duplicate masters: saved = the last template (clean), an ambiguous value (drift), and a legacy 0 first with 0.062 last (SHADOW, R 1.24).
  - Recompute replay drift is 0.00 on every case, and a negative control proved the checker can fail.

## 5. Reading the result — decision tree (BA-coordinator)

1. **`00_code_state` does not show the expected served bundle** (`_draftFlagVariables` present, `_masterBodyVarNameSet` absent, `?v=178`): prod state differs from this WO's premise. STOP and re-baseline before anything else.
2. **D SHADOW costings = 0** (PIN_DRIFT is informational) → no data remediation. Proceed to §6 (prod deploy WO). If "in window but no ui_snapshot" or `NO_SNAPSHOT_POSSIBLE_SHADOW` is non-zero, list those costings for a manual look first.
3. **D SHADOW costings > 0** → list them with F deltas. Per costing, decide by status:
   - `pending`: reopen and re-save after 94ed70b is on prod. The edit pins the saved zeros (by design), so the pair must be re-selected or the thickness re-entered. That remedy needs its own tested WO.
   - `accepted` / `declined` / quoted-to-customer: a commercial decision (Burt/BA). **Never auto-fix data.**
   - A validated reference in E on a flagged costing: re-mark it after re-save.
4. **E rows without D hits** → informational; fingerprints will drift after the fix.
5. **G `heal_v2` or `ambiguous` non-empty** → review before deploying (render and seeding change on those bodies). Ambiguous heals need BA input.

## 6. Follow-on: prod deploy WO (draft outline — not part of this audit)

- **Target:** `94ed70b` (#184 + #185 + #186). `git diff e5c7837..94ed70b -- backend/app` has **no `.py`**: JS + templates only (`?v=180`). A service restart isn't required for the code, but is harmless and recommended.
- **Prod checkout:** currently a detached HEAD at `04b332f`. Deploy by pasted block: fetch, checkout `94ed70b`, verify served markers, restart.
- **#184 seeding:** `tools/set_manni_flag_defaults.py` defaults for the prod Manni RIGIDS CB (trailer 41) are a separate, Michael-approved paste. Only masterless bodies use `flagVarDefault`.
- **Proof:** served `calculator.js` sha256 == `git show 94ed70b:backend/app/static/js/calculator.js`, then a FREEZER-class body editor check on both front doors (LAN IP + CF domain; CF purge per the two-front-doors note).

## 7. Kit contents

- `run-prod-audit.ps1` — Windows launcher (scp → ssh -t → scp back); prompts are yours.
- `kit/audit.sh` — VM wrapper: code-state probes plus the read-only Python run. No `set -e`; every step prints its own exit code.
- `kit/prod_audit.py` — sections A–G. The same script runs on dev from `backend/`.
