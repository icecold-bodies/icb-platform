# Prod deploy — v1.50.0 → v1.51 "PU insulation foam grade, repair quote print modes, opt-in tips" (25 Aug 2026)

Target: **`https://192.168.0.251/mes-app/`** (ICB intranet VM, `/opt/icb-platform`,
service `icb-backend`, `uvicorn --workers 4`).

| | |
|---|---|
| Prod is at | `e182c97` = tag `v1.50.0` (deployed 22 Aug 06:58) — **step 1 asserts this; STOP if it prints anything else** |
| Deploying to | **`__TARGET_SHA__`** (`__TARGET_FULL__`) |
| Commits | **4 merges + 2 doc commits** — #169, #168, #170, #171 (everything since v1.50.0) |
| DB migration | **YES — one**: `0046` (PU foam normalisation). Prod must read `0045` before and `0046` after |
| **Data mutation** | **YES — this migration REWRITES PU FOAM PRICES.** See "The one that needs care" below. Run the pre-flight first |
| DB backup first | **YES** — on-demand run of `icb-pg-backup`, before anything else |
| Frontend rebuild | **YES** — 5 files under `frontend/src` from #169 |
| Service restart | **YES** — backend Python changed (#168) |
| New deps / env vars | **none** — no `requirements*.txt` or `package.json` change; **prod `.env` untouched** (Marnus-owned) |
| Downtime | ~30–60 s (stop → migrate → start). Build runs *before* the stop |

## What lands

- **#169 `537af2e`** — repair quote print modes (BREAKDOWN default), editable `Veh reg nr:` caption, board shows the R-number. Ships the 5 frontend files.
- **#168 `dfadc70`** — **PU insulation foam grade**: one selection per costing under BODY OPTIONS, `32D PU FOAM` (default) / `4G FOAM`. Ships migration **0046** and `calculator.js?v=170`.
- **#170 `b44982a`** — one `calculator.js` tag, not two. #168 and #169 each bumped the cache-bust and the merge auto-joined both tags side by side, so every calculator load fetched the file twice and threw `SyntaxError: Identifier 'allCustomers' has already been declared`. Lands `?v=172`.
- **#171 `__TIPS_SHA__`** — BOM hover tips are **opt-in, off by default**, behind a `Tips` checkbox in the Bill of Materials header. Covers both the coloured price bubbles and the large hover FORMULA panel. Lands `calculator.js?v=173` and `style.css?v=20`.

## ⚠ The one that needs care — 0046 rewrites prices

Burt hand-edited his workbook to switch a body between 32D PU FOAM and 4G FOAM, which baked
the grade into the stored unit price of some categories. The MES now stores the **32D** price
and derives 4G at calculation time (`× 5875/4310 = 1.36311`), so 0046 normalises the rows that
were baked at 4G **down** onto their 32D value.

**Two categories will show PU prices ~26.6 % lower than they did yesterday** — on dev those are
`EXPLOSIVE 4.9 AND UP` and `MEAT HANGER LARGE`. That is the ratified normalisation, not a
fault: ticking **4G FOAM** in BODY OPTIONS restores the previous number **to the cent**. Tell
Burt before he opens one of those, or it reads as a pricing error.

**Rows the migration cannot classify are left untouched and reported.** On dev that is all five
`RHINORANGE TRAILER` rows, which sit on a coherent internal rate of 6373.80 derived from
neither sheet price. Prod may differ — the pre-flight below says exactly.

Every rewrite is journalled into `icb_costings.pu_foam_normalisation` (bom_id, old/new price,
classification), so the downgrade replays the old prices back **byte-exact**.

## Pre-flight — READ-ONLY, run this FIRST and send the CA the output

Writes nothing. Reproduces the migration's classifier in SQL and reports what it *would* do, so
prod's outcome is known before prod is touched. (Verified against dev: restoring the 9 rows to
their pre-migration values inside a rolled-back transaction, this SQL predicted the identical
buckets and the identical after-prices to six decimals.)

```bash
cat > /tmp/icb-preflight-0046.sh <<'ICBEOF'
DB=icb_platform
echo "== alembic now (expect 0045) =="
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current'
echo "== what 0046 WOULD do — nothing is written =="
sudo -u postgres psql -d "$DB" -f /tmp/icb-preflight-0046.sql
ICBEOF
```

The `.sql` file is staged separately by the CA (it is long). Ask for it, drop it at
`/tmp/icb-preflight-0046.sql`, then `bash /tmp/icb-preflight-0046.sh`.

**Expected:** a bucket count (`32D`, `4G`, `4G~2.99`, `SHARED-DEFAULT`, `NO-THICKNESS`,
`UNCLASSIFIED`), then the exact rows that will be rewritten with their before/after prices, then
the rows that will be refused. **Send that output to the CA before deploying.** If `4G` +
`4G~2.99` is zero, the migration is a no-op on prod and the price warning above does not apply.

## Cache-busts

`calculator.js?v=169` → **`?v=173`**, and `style.css?v=19` → **`?v=20`** in `base.html`. The CSS
bump is load-bearing: a cached stylesheet plus the new JS gives no tips at all, even with the
box ticked. Anyone holding an old calculator tab keeps the old JS until they reload — that has
read as "the fix isn't deployed" before. Reload the tab first.

## Who runs it

**Michael.** `/opt/icb-platform` is `icb:icb`, `mickeyger` is not in that group, and sudo is
password-required — the CA cannot execute this. From Windows: `ssh icb-mes-prod` (or
`ssh mickeyger@192.168.0.251`), then paste the block. The CA verifies from outside afterwards.

> ⚠ **Do not use `Push-ToProd.ps1`.** Its Deploy path broke four ways on its first real use and
> the fixes have never been run end to end. v1.49.1, v1.49.2, v1.50.0 and this one all go out
> by pasted block.

> ⚠⚠⚠ **Never paste a bare `set -euo pipefail` into the login shell.** The block below writes a
> script through a quoted heredoc and runs it in a child `bash`: a stray bracketed-paste marker
> is data, and a failure ends the *script*, never your session. `sudo` still prompts fine — it
> reads `/dev/tty`, not stdin.

## Deploy — paste as ONE block on the prod VM

```bash
cat > /tmp/icb-deploy-v1510.sh <<'ICBEOF'
set -euo pipefail
DB=icb_platform
REPO=/opt/icb-platform
TARGET=__TARGET_FULL__
BASELINE=e182c9780358a2c77b355395a4209a2a8569dc36

echo "== STEP 1: rollback anchor — prod must be exactly v1.50.0 =="
cd "$REPO"
HEAD_NOW=$(git rev-parse HEAD)
echo "ROLLBACK COMMIT: $HEAD_NOW"; git tag --points-at HEAD
test "$HEAD_NOW" = "$BASELINE" || { echo "PROD IS NOT AT v1.50.0 - STOP, investigate"; exit 1; }

echo "== STEP 2: schema anchor — alembic must read 0045 =="
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current' | tee /tmp/alembic-before-v1510.txt
grep -q 0045 /tmp/alembic-before-v1510.txt || { echo "ALEMBIC IS NOT AT 0045 - STOP, someone part-deployed"; exit 1; }

echo "== STEP 3: fresh DB backup BEFORE anything (nightly is ~02:30, too old) =="
sudo -u postgres psql -Atc "select 1 from pg_database where datname='$DB'" | grep -q 1 || { echo "DB '$DB' NOT FOUND - STOP"; exit 1; }
sudo systemctl start icb-pg-backup.service
sudo systemctl status icb-pg-backup.service --no-pager | tail -3 || true   # a FINISHED oneshot exits 3 — without the guard, pipefail kills the run silently
FRESH=$(sudo find /var/backups/postgres -name "*.dump.gz" -mmin -10 | sort | tail -1)
test -n "$FRESH" && echo "FRESH BACKUP: $FRESH" || { echo "NO FRESH BACKUP FOUND - STOP"; exit 1; }

echo "== STEP 4: PU foam prices BEFORE (0046 is judged against this) =="
sudo -u postgres psql -d "$DB" -c "
  select b.id, t.name as body, b.bom_section as sect, b.unit_price_override as price
    from icb_costings.bill_of_materials b
    join icb_costings.materials m on m.id = b.material_id
    left join icb_costings.trailer_types t on t.id = b.trailer_type_id
   where upper(btrim(m.name)) in ('PU','PU FOAM')
     and coalesce(b.is_body_option,false) = false
     and b.unit_price_override is not null
   order by t.name, b.bom_section" | tee /tmp/pu-before-v1510.txt

echo "== STEP 5: code — fast-forward to the exact SHA =="
sudo -u icb git -C "$REPO" fetch origin --tags || true   # tag-clobber warnings here are known benign noise
sudo -u icb git -C "$REPO" merge --ff-only "$TARGET"
test "$(git -C "$REPO" rev-parse HEAD)" = "$TARGET" && echo "AT v1.51 target" || { echo "WRONG COMMIT - STOP"; exit 1; }

echo "== STEP 6: rebuild the SPA (service still up, old bundle keeps serving) =="
sudo -u icb bash -lc 'cd /opt/icb-platform/frontend && npm run build'
ls -la "$REPO/frontend/dist/index.html"

echo "== STEP 7: stop -> migrate -> start (the only downtime window) =="
TS_BEFORE=$(systemctl show icb-backend -p ActiveEnterTimestamp --value); echo "was up since: $TS_BEFORE"
sudo systemctl stop icb-backend
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic upgrade head' 2>&1 | tee /tmp/alembic-run-v1510.txt
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current' | tee /tmp/alembic-after-v1510.txt
grep -q 0046 /tmp/alembic-after-v1510.txt || { echo "MIGRATION DID NOT REACH 0046 - service is STOPPED - see 'If it stops partway'"; exit 1; }
sudo systemctl start icb-backend
sleep 8
systemctl is-active icb-backend
TS_AFTER=$(systemctl show icb-backend -p ActiveEnterTimestamp --value); echo "now up since: $TS_AFTER"
test "$TS_BEFORE" != "$TS_AFTER" || { echo "TIMESTAMP DID NOT CHANGE - stale process - STOP"; exit 1; }

echo "== STEP 8: boot must be clean — expect 4 workers, 0 bootstrap failures =="
W=$(sudo journalctl -u icb-backend --since '-3 min' --no-pager | grep -Ec 'Application startup complete' || true)
echo "workers started: $W"; test "$W" = "4" || { echo "EXPECTED 4 WORKERS, got $W - STOP"; exit 1; }
B=$(sudo journalctl -u icb-backend --since '-3 min' --no-pager | grep -c 'BOOTSTRAP FAILED' || true)
echo "bootstrap failures: $B"; test "$B" = "0" || { echo "BOOTSTRAP FAILED IN LOG - STOP"; exit 1; }

echo "== STEP 9: what 0046 actually did — the journal IS the record =="
echo "--- classification the migration logged ---"
grep -E '0046 PU foam' /tmp/alembic-run-v1510.txt || echo "(no 0046 log lines - unexpected)"
echo "--- journal (every rewrite, with its old price) ---"
sudo -u postgres psql -d "$DB" -c "select bom_id, trailer_name, bom_section, thickness_m, old_price, new_price, classification from icb_costings.pu_foam_normalisation order by trailer_name, bom_section"
echo "--- the derived ratio setting (seeded, guarded) ---"
sudo -u postgres psql -d "$DB" -c "select key, value from icb_costings.admin_settings where key='costings.pu_foam_4g_factor'"
echo "--- every rewritten row is now EXACTLY old/1.36311 ---"
sudo -u postgres psql -d "$DB" -c "
  select count(*) filter (where abs(b.unit_price_override - j.new_price) > 0.000001) as mismatched
    from icb_costings.pu_foam_normalisation j
    join icb_costings.bill_of_materials b on b.id = j.bom_id"

echo "== STEP 10: smoke — health, both cache-busts, the new code in the served bytes =="
curl -k -s https://127.0.0.1/health; echo
C1=$(curl -k -s https://127.0.0.1/static/js/calculator.js | grep -c 'insulation-foam-block' || true)
echo "foam markers: $C1"; test "$C1" -ge "1" || { echo "SERVED calculator.js IS STALE (no foam block) - STOP"; exit 1; }
C2=$(curl -k -s https://127.0.0.1/static/js/calculator.js | grep -c '_syncPriceTitles' || true)
echo "tips markers: $C2"; test "$C2" -ge "1" || { echo "SERVED calculator.js IS STALE (no tips) - STOP"; exit 1; }
C3=$(curl -k -s https://127.0.0.1/static/css/style.css | grep -c 'data-tips' || true)
echo "css gate refs: $C3"; test "$C3" -ge "1" || { echo "SERVED style.css IS STALE - STOP"; exit 1; }
D1=$(ls "$REPO"/frontend/dist/assets/*.js 2>/dev/null | head -1 || true)
echo "spa bundle: ${D1:-MISSING}"; test -n "$D1" || { echo "SPA BUNDLE MISSING - STOP"; exit 1; }
echo "== DONE — compare every number against the Expected table in the runbook =="
ICBEOF

bash /tmp/icb-deploy-v1510.sh
```

## Expected

| Step | Expected |
|---|---|
| 1 | `ROLLBACK COMMIT: e182c97…` and tag `v1.50.0` |
| 2 | `0045 (head)` |
| 3 | backup unit runs; a fresh `.dump.gz` under 10 minutes old |
| 4 | the PU price list — keep this, it is the before-picture |
| 5 | `AT v1.51 target`; tag-clobber warnings during fetch are known benign noise |
| 6 | a fresh `dist/index.html`; build ~10 s |
| 7 | alembic prints `0046`; `0046 (head)`; the two timestamps differ |
| 8 | **4** and **0** |
| 9 | classification lines matching the **pre-flight**; journal row count == the pre-flight's `4G` + `4G~2.99`; factor `1.363109048723898`; **`mismatched` = 0** |
| 10 | `{"status":"ok"}` · foam markers ≥1 · tips markers ≥1 · css gate refs ≥1 · one `dist/assets/…js` |

Step 9 is the one that matters most. **`mismatched` must be 0** and the journal must contain
exactly the rows the pre-flight predicted — nothing else in the BOM should have moved.

## If it stops partway

| Died at | State | Do |
|---|---|---|
| 1–4 | nothing changed | fix the reported problem, re-run the block from the top (re-runnable) |
| 5–6 | new code on disk, old code running | safe indefinitely; re-run (steps 1–2 will now fail their asserts — expected; ask the CA) |
| 7 before `alembic` | service stopped, schema 0045 | `sudo systemctl start icb-backend` puts v1.50.0 back; then investigate |
| 7 after `alembic` | service stopped, schema 0046 | **finish forward** — `sudo systemctl start icb-backend`, continue from step 8. Old code at 0046 is the one mix to avoid: it would quote the normalised 32D prices with no way to select 4G |
| 8–10 | deployed, verifying | investigate before letting users in; the CA can drive this |

## CA verification after the paste

Read-only from the Windows side (VPN): `https://192.168.0.251/health` is 200; the served
`calculator.js` is byte-identical to `git show __TARGET_SHA__:backend/app/static/js/calculator.js`
and carries `insulation-foam-block` and `_syncPriceTitles`; the served `style.css` carries
`body[data-tips="on"]`; and — with Michael logged in — a costing on a PU body shows the
**Insulation foam** pair defaulting to 32D, with the BOM header's **Tips** box unticked and no
tooltip on hover.

## Rollback

Code back + undo 0046 (its downgrade replays the journal, restoring every old price
byte-exact), then rebuild and restart:

```bash
cat > /tmp/icb-rollback-v1510.sh <<'ICBEOF'
set -euo pipefail
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic downgrade 0045'
sudo -u icb git -C /opt/icb-platform reset --hard e182c9780358a2c77b355395a4209a2a8569dc36
sudo -u icb bash -lc 'cd /opt/icb-platform/frontend && npm run build'
sudo systemctl restart icb-backend
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current'
ICBEOF

bash /tmp/icb-rollback-v1510.sh
```

Any approved costing saved **after** this deploy keeps its own saved prices either way —
`result_json` is frozen at Approve and is never re-derived from the BOM.

## OUTCOME

_(filled in after the run)_
