# Prod deploy — v1.52 "September 2026 price + description update" (STAGED — not yet run)

Target: **`https://192.168.0.251/mes-app/`** (ICB intranet VM, `/opt/icb-platform`,
service `icb-backend`, `uvicorn --workers 4`, DB **`icb_platform`**).

> **THIS RUNBOOK IS STAGED IN ADVANCE. Michael runs it — and only after ALL THREE
> gates are true:**
> 1. Michael + Nadie have clicked through the September prices on dev :8000;
> 2. sales has been told prices are changing (the "Updated Sept 2026" badges and
>    new totals appear the moment this lands);
> 3. the BA has given the go and filled in `TARGET` below with the squash-merge SHA.

| | |
|---|---|
| Prod is at | fill in at go-time — step 1 prints it and it becomes the ROLLBACK anchor |
| Deploying to | **`TARGET` = the v1.52 squash-merge SHA — FILL IN BELOW, the script refuses the placeholder** |
| DB migration | **YES — one**: `0047` (adds `bill_of_materials.price_updated_at`, nullable; additive, no data rewrite). Prod must read `0046` before and `0047` after |
| **Data mutation** | **YES — the September price import.** Dev reference: **431 line actions** (371 line updates, 55 PU covered, 5 PU rescales), 124 override resets, 24 in-place + 64 created materials, 4G factor → `1.3170731707317074`. Prod runs its own DRY-RUN first (step 5) and **STOPS if the numbers stray far from these** |
| DB backup first | **YES, twice** — on-demand `icb-pg-backup` (step 3) AND the import script's own CSV table backups (automatic, into `/var/backups/icb-september-2026/`) |
| Frontend rebuild | **NO** — zero `frontend/src` files in this lane (badge lives in the legacy calculator JS/CSS) |
| Service restart | **YES** — backend Python changed (`trailers.py`, `database.py`) |
| New deps / env vars | **none**; **prod `.env` untouched** (Marnus-owned) |
| Downtime | ~30 s (stop → migrate → apply → start). The ff + dry-run happen while the old service keeps serving |
| Reversible | **byte-exact** — proven on dev: apply → revert → re-apply left all five written tables hash-identical. The journal in `/var/backups/icb-september-2026/` is the revert input |

## What lands

- **Migration 0047** — `bill_of_materials.price_updated_at` (line-level badge stamp).
- **The September import** (`backend/tools/september_price_import.py`) — Burt's
  reissued September prices + descriptions on 22 bodies, manifest-driven
  (`docs/audit/september_price_update/september_change_manifest.csv`, BA-diffed and
  independently reconciled). Manni family + Sheet1 are refused in code (Michael's
  ruling); AELER PANELS has no MES body and falls away.
- **The 4G factor update** — `costings.pu_foam_4g_factor` `1.363109…` → `5400/4100 =
  1.3170731707317074` in the same apply (September moves 32D 4310→4100, 4G 5875→5400).
- **"Updated Sept 2026" badges** — on every imported line, in both calculators,
  self-expiring 30 days after the apply; visible regardless of the Tips checkbox.
  Cache-busts: `calculator.js?v=174`, `calculator2.js?v=126`, `style.css?v=21`.

## ⚠ Three things to know before running

1. **The import plans against PROD's own data at run time.** Prod's BOM has its own
   override history, so the dry-run counts will not be byte-identical to dev's.
   Small drift (a handful of rows moving between matched/unmatched/review) is
   expected; **large drift is a STOP** — send `/tmp/sept-dryrun.txt` to the CA/BA.
2. **The apply is one-shot by design.** After it runs, the old descriptions are gone,
   so the script REFUSES a second `--apply` while September stamps are fresh
   (proven guard). To redo: `--revert` the journal first.
3. **Cloudflare**: the badge assets ride new `?v=` query strings, so the domain door
   gets fresh JS/CSS without a purge. After the deploy Michael should still purge
   the CF cache (Dashboard → Caching → Purge Everything) — belt and braces for any
   extension-cached stragglers, same as the #173 lesson.

## Who runs it

**Michael.** `/opt/icb-platform` is `icb:icb` and sudo is password-required — the CA
cannot execute this. From Windows: `ssh icb-mes-prod` (or `ssh mickeyger@192.168.0.251`),
then paste the block. The CA live-tails from outside and verifies afterwards.

> ⚠⚠⚠ **Never paste a bare `set -euo pipefail` into the login shell.** The block
> writes a script through a quoted heredoc and runs it in a child `bash`.

## Deploy — paste as ONE block on the prod VM (after filling in TARGET)

```bash
cat > /tmp/icb-deploy-v152.sh <<'ICBEOF'
set -euo pipefail
DB=icb_platform
REPO=/opt/icb-platform
OUTDIR=/var/backups/icb-september-2026
TARGET=FILL_IN_SQUASH_MERGE_SHA_BEFORE_RUNNING

echo "== STEP 0: refuse the placeholder =="
case "$TARGET" in FILL_IN*) echo "TARGET NOT FILLED IN - STOP"; exit 1;; esac

echo "== STEP 1: rollback anchor — record exactly where prod is =="
cd "$REPO"
HEAD_NOW=$(git rev-parse HEAD)
echo "ROLLBACK COMMIT: $HEAD_NOW"; git tag --points-at HEAD || true

echo "== STEP 2: schema anchor — alembic must read 0046 =="
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current' | tee /tmp/alembic-before-v152.txt
grep -q 0046 /tmp/alembic-before-v152.txt || { echo "ALEMBIC IS NOT AT 0046 - STOP, investigate"; exit 1; }

echo "== STEP 3: fresh DB backup BEFORE anything =="
sudo -u postgres psql -Atc "select 1 from pg_database where datname='$DB'" | grep -q 1 || { echo "DB '$DB' NOT FOUND - STOP"; exit 1; }
sudo systemctl start icb-pg-backup.service
sudo systemctl status icb-pg-backup.service --no-pager | tail -3 || true   # finished oneshot exits 3 — guard keeps pipefail quiet
FRESH=$(sudo find /var/backups/postgres -name "*.dump.gz" -mmin -10 | sort | tail -1)
test -n "$FRESH" && echo "FRESH BACKUP: $FRESH" || { echo "NO FRESH BACKUP FOUND - STOP"; exit 1; }
sudo mkdir -p "$OUTDIR" && sudo chown icb:icb "$OUTDIR"

echo "== STEP 4: code — fast-forward to the exact SHA (old python keeps running) =="
sudo -u icb git -C "$REPO" fetch origin --tags || true
sudo -u icb git -C "$REPO" merge --ff-only "$TARGET"
test "$(git -C "$REPO" rev-parse HEAD)" = "$TARGET" && echo "AT v1.52 target" || { echo "WRONG COMMIT - STOP"; exit 1; }

echo "== STEP 5: DRY-RUN the import against PROD data (read-only) — the go/no-go picture =="
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/python tools/september_price_import.py --manifest ../docs/audit/september_price_update/september_change_manifest.csv --out-dir '"$OUTDIR"'/dryrun --env-tag prod' 2>&1 | tee /tmp/sept-dryrun.txt
echo ""
echo ">>> COMPARE against the dev reference: 431 actions / 124 resets / 1 review / 1 unmatched / 0 ambiguous."
echo ">>> If unmatched or review are more than a HANDFUL higher, or actions differ by more than ~20: STOP here"
echo ">>> (nothing has been written) and send /tmp/sept-dryrun.txt to the CA/BA."
read -r -p "Type APPLY to continue past the dry-run gate: " GATE </dev/tty
test "$GATE" = "APPLY" || { echo "not confirmed - STOP (nothing written)"; exit 1; }

echo "== STEP 6: stop -> migrate 0047 -> APPLY -> start (the only downtime window) =="
TS_BEFORE=$(systemctl show icb-backend -p ActiveEnterTimestamp --value); echo "was up since: $TS_BEFORE"
sudo systemctl stop icb-backend
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic upgrade head' 2>&1 | tee /tmp/alembic-run-v152.txt
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current' | tee /tmp/alembic-after-v152.txt
grep -q 0047 /tmp/alembic-after-v152.txt || { echo "MIGRATION DID NOT REACH 0047 - service is STOPPED - see 'If it stops partway'"; exit 1; }
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/python tools/september_price_import.py --manifest ../docs/audit/september_price_update/september_change_manifest.csv --out-dir '"$OUTDIR"' --apply --env-tag prod' 2>&1 | tee /tmp/sept-apply.txt
grep -q "APPLIED. journal:" /tmp/sept-apply.txt || { echo "APPLY DID NOT REPORT SUCCESS - service is STOPPED - do not start; call the CA/BA"; exit 1; }
sudo systemctl start icb-backend
sleep 8
systemctl is-active icb-backend
TS_AFTER=$(systemctl show icb-backend -p ActiveEnterTimestamp --value); echo "now up since: $TS_AFTER"
test "$TS_BEFORE" != "$TS_AFTER" || { echo "TIMESTAMP DID NOT CHANGE - stale process - STOP"; exit 1; }

echo "== STEP 7: boot must be clean — expect 4 workers, 0 bootstrap failures =="
W=$(sudo journalctl -u icb-backend --since '-3 min' --no-pager | grep -Ec 'Application startup complete' || true)
echo "workers started: $W"; test "$W" = "4" || { echo "EXPECTED 4 WORKERS, got $W - STOP"; exit 1; }
B=$(sudo journalctl -u icb-backend --since '-3 min' --no-pager | grep -c 'BOOTSTRAP FAILED' || true)
echo "bootstrap failures: $B"; test "$B" = "0" || { echo "BOOTSTRAP FAILED IN LOG - STOP"; exit 1; }

echo "== STEP 8: what the apply actually did — journals + the factor =="
sudo -u postgres psql -d "$DB" -c "select value from icb_costings.admin_settings where key='costings.pu_foam_4g_factor'" | tee /tmp/factor-after.txt
grep -q "1.3170731707317074" /tmp/factor-after.txt || { echo "4G FACTOR NOT UPDATED - STOP"; exit 1; }
sudo -u postgres psql -d "$DB" -Atc "select count(*) from icb_costings.bill_of_materials where price_updated_at is not null"
sudo -u postgres psql -d "$DB" -Atc "select count(*) from icb_costings.materials where last_bulk_update_note = 'September 2026 price update'"
echo "(both counts should be in the same ballpark as the apply summary lines above)"

echo "== STEP 9: smoke — health + all three cache-busted assets carry the badge code =="
H=$(curl -k -s -o /dev/null -w '%{http_code}' https://127.0.0.1/health); echo "health: $H"; test "$H" = "200" || { echo "HEALTH NOT 200 - STOP"; exit 1; }
C1=$(curl -k -s "https://127.0.0.1/static/js/calculator.js?v=174" | grep -c 'price-updated-badge' || true)
echo "calc1 badge markers: $C1"; test "$C1" -ge "1" || { echo "SERVED calculator.js IS STALE - STOP"; exit 1; }
C2=$(curl -k -s "https://127.0.0.1/static/js/calculator2.js?v=126" | grep -c 'price-updated-badge' || true)
echo "calc2 badge markers: $C2"; test "$C2" -ge "1" || { echo "SERVED calculator2.js IS STALE - STOP"; exit 1; }
C3=$(curl -k -s "https://127.0.0.1/static/css/style.css?v=21" | grep -c 'price-updated-badge' || true)
echo "css badge rules: $C3"; test "$C3" -ge "1" || { echo "SERVED style.css IS STALE - STOP"; exit 1; }
echo "== DONE — now do the browser checks in the runbook, on the DOMAIN door =="
ICBEOF

bash /tmp/icb-deploy-v152.sh
```

## Expected

| Step | Expected |
|---|---|
| 1 | the current prod SHA — write it down, it is the rollback anchor |
| 2 | `0046 (head)` |
| 3 | fresh `.dump.gz` under 10 minutes old; `$OUTDIR` created |
| 4 | `AT v1.52 target` |
| 5 | plan summary ≈ dev reference (431/124/1/1/0); the interactive gate waits for `APPLY` |
| 6 | alembic prints `0047`; apply prints `APPLIED. journal: …`; timestamps differ |
| 7 | **4** and **0** |
| 8 | factor `1.3170731707317074`; stamped-line count ≈ apply's `lines=`; stamped materials ≈ 88 |
| 9 | health 200; all three badge-marker counts ≥ 1 |

## After the paste — browser checks (Michael, on `https://mes.icecoldgrp.online`)

1. Purge the Cloudflare cache (Dashboard → Caching → Purge Everything).
2. **Hard-reload** the calculator (old tabs keep old JS — the stale-tab trap).
3. Open **CHILLER 2.3 METER** on Cost Calculator: FRONT shows **Rhinotex 1150 BW**
   with a green **Updated Sept 2026** badge (Tips box UNTICKED — the badge must
   show anyway).
4. Open **CHESTER SPEC MEAT BODY**: badges on its PU lines; total meaningfully up
   vs August (dev showed +22.5% at cost level — that body was underquoting).
5. Any saved/approved costing recalled: prices unchanged (frozen); validated
   references may show drift warnings — **expected**, not a defect.

## CA verification after the paste (read-only, from Windows)

`https://192.168.0.251/health` 200; served `calculator.js?v=174` /
`calculator2.js?v=126` / `style.css?v=21` each byte-identical to `git show
TARGET:…` and carrying `price-updated-badge`; both doors probed (IP and domain).

## If it stops partway

| Died at | State | Do |
|---|---|---|
| 0–3 | nothing changed | fix the reported problem, re-run from the top |
| 4–5 | new code on disk, old python running, no data changed | safe indefinitely; re-run from the top (step 2 still passes — 0046) |
| 6 before alembic | service stopped, schema 0046, no data changed | `sudo systemctl start icb-backend` restores status quo |
| 6 after alembic, before/during apply | service stopped, schema 0047, data possibly PARTIAL — **the apply is a single transaction, so a failed apply wrote NOTHING** | `sudo systemctl start icb-backend`; old code + 0047 is safe (additive column); investigate with the CA |
| 6 after apply | September prices live | finish forward from step 7 |
| 7–9 | deployed, verifying | investigate before letting users in; CA can drive |

## Rollback (full: data + schema + code)

```bash
cat > /tmp/icb-rollback-v152.sh <<'ICBEOF'
set -euo pipefail
OUTDIR=/var/backups/icb-september-2026
ROLLBACK_SHA=FILL_IN_THE_STEP1_ANCHOR
case "$ROLLBACK_SHA" in FILL_IN*) echo "FILL IN THE ANCHOR - STOP"; exit 1;; esac
J=$(ls "$OUTDIR"/apply_journal_prod_*.json | sort | tail -1)
echo "reverting journal: $J"
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/python tools/september_price_import.py --revert '"$J"' --out-dir '"$OUTDIR"' --env-tag prod'
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic downgrade 0046'
sudo -u icb git -C /opt/icb-platform reset --hard "$ROLLBACK_SHA"
sudo systemctl restart icb-backend
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current'
ICBEOF

bash /tmp/icb-rollback-v152.sh
```

Order matters: the data revert runs FIRST (it needs the v1.52 code + journal on
disk), then the schema, then the code. Byte-exact restoration was proven on dev
(all five written tables hash-identical after apply → revert). Approved costings
are frozen in `result_json` either way.

## OUTCOME — deployed 4 Sep 2026 08:42 SAST, all asserts green

Michael ran the staged script over ssh (scripts scp-staged by the CA, sha256-verified
byte-identical). Two operational notes from the run, both handled by design:

1. **First run stopped at the dry-run gate** — `yes` was typed where the gate demands
   the exact word `APPLY`. Nothing was written; steps 1–5 had already taken the fresh
   backup and fast-forwarded the repo, so re-runs then refused at the step-1 baseline
   assert (as designed: "already fast-forwarded" is indistinguishable from
   "part-deployed" to that assert). The CA staged `/tmp/icb-deploy-v152-resume.sh`
   asserting the mid-state (HEAD=target, schema 0046, anchor file intact) and the run
   completed through it.
2. **The prod dry-run diverged from the dev reference** — 410 actions / 61 resets /
   8 review / 22 unmatched (dev: 431 / 124 / 1 / 1). CA verdict before APPLY: safe.
   The divergence decomposes into (a) 7 of 8 review rows = the known v1.51 prod PU
   oddities already on Burt's list (CHILLER LARGE ×5 + CHILLER MEDIUM thickness
   wiring, MEAT HANGER SMALL-MEDIUM bom 6229), plus one icecream-4.8 FRONT PU whose
   prod price bakes a different thickness (stored 430.54 = 32D@0.1 vs the sheet's
   0.12 flavour) — all parked, nothing written; (b) 22 unmatched = prod lines under
   different/older names (mostly FLOOR `EXT GRP SKIN 2*300` and `4MM PF PLYWOOD`) —
   skipped per default 2, and since September was mostly reductions the skip errs
   high, the safe direction; (c) every writing action carries a manifest value
   (291 down / 103 up; the largest jumps trace to manifest rows on staler prod
   baselines).

| | |
|---|---|
| Baseline | `e2dbfd5` (#172 line head) confirmed; anchor file written; fresh dumps at both runs |
| Target | **`cd763c8`** reached; alembic `0046 → 0047` |
| Apply | **410 line actions**, 23 in-place + 61 created materials, 23 `price_history`, 121 `bom_override_history`; journal `apply_journal_prod_20260904T064218Z.json`; pre-apply table backup `pre_apply_prod_20260904T064218Z` (materials=808, bom=9012) — both under `/var/backups/icb-september-2026/` |
| Factor | `costings.pu_foam_4g_factor = 1.3170731707317074` ✓ |
| Boot | 4 workers, 0 bootstrap failures (script asserts passed); ActiveEnterTimestamp moved |
| Smoke | health 200 on BOTH doors; `calculator.js?v=174` / `calculator2.js?v=126` / `style.css?v=21` each carry `price-updated-badge` on the IP door AND the domain door (first `?v=174` fetch was a CF MISS→origin, then edge-cached the NEW bytes) |
| CA byte-identity | served `calculator.js` / `calculator2.js` / `style.css` sha256-identical to `git show cd763c8:…` |

Prod run artifacts committed for BA/Burt review under
`docs/audit/september_price_update/prod/`: the apply journal (the `--revert` input),
the prod BEFORE/AFTER plan, excluded-scope (incl. the 22 unmatched), review rows and
override survivors.

**No tag cut** — the release tag stays the BA-coordinator's call.

**Follow-ups handed to BA/Burt** (nothing silently dropped): the 22 prod unmatched
rows (September prices not applied to lines whose prod names differ — they keep
their older, higher prices until named/mapped); the 8 review rows above; the shared
per-section PU material defaults (0046 guard upheld, standing question); Sheet1 vs
BAKERY BODIES conflicts (§3.0). The "Updated Sept 2026" badges self-expire ~4 Oct 2026.
