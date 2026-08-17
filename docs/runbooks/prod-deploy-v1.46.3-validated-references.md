# Prod deploy — v1.45 → v1.46.3 "Validated references" (11 Aug 2026)

Target: **`https://192.168.0.251/mes-app/`** (ICB intranet VM, `/opt/icb-platform`,
service `icb-backend`, `uvicorn --workers 4`).

| | |
|---|---|
| Prod is at | `f4b1e1d` (v1.45.2, deployed 10 Aug) |
| Deploying to | `cfc7480` — tip of `backport/v1.39-base` |
| Commits | **5** — #121, #122, #123, #124, #125 (all one lane: Validated references) |
| DB migration | **YES — 0039** (`0038 → 0039`) |
| Frontend rebuild | **YES** — the range touches `frontend/src` (3 files) |
| New env vars | **none** |
| New permission key | `costings.validated_refs_manage` — seeded automatically by the startup bootstrap |

## Why this one needs more than the usual code-pull

Previous deploys in this line were backend-only restarts. This one is **not**:

1. **Migration 0039** creates `icb_costings.validated_references` (+ a partial unique
   index) and seeds one `admin_settings` row (`costings.validated_ref_tolerance_pct = 2`).
   Purely additive — no existing table or column is altered, no data is rewritten — and
   inspector-guarded, so a re-run is a no-op. `alembic upgrade head` is **not** run by the
   app at startup, so it must be run by hand.
2. **`npm run build`** is required. #121 changed `CostingDetail.tsx`, `AppDataContext.tsx`
   and `costingsData.ts`. Prod serves the built `frontend/dist` (last built 10 Aug 14:19);
   without a rebuild the MES costing-detail page keeps the old bundle and the new
   permission gating never reaches the SPA.
3. The new permission key rides the catalogue-driven startup bootstrap. Prod already has
   the #120 advisory lock, so all four workers can seed it safely.

## Who runs it

**Michael.** `/opt/icb-platform` is owned by `icb:icb`, `mickeyger` is not in that group,
and `sudo` on the VM is password-required — so the CA cannot execute this. Paste the block
below on the VM as `mickeyger`; the CA verifies from outside afterwards.

## Deploy — paste as ONE block on the prod VM

```bash
set -euo pipefail

# 0. fresh DB backup BEFORE the migration (the nightly one is ~02:30; take one now)
sudo systemctl start icb-pg-backup.service
sleep 5
sudo systemctl status icb-pg-backup.service --no-pager | tail -5

# 1. record the rollback anchors
cd /opt/icb-platform
echo "ROLLBACK COMMIT: $(git rev-parse HEAD)"
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current' \
  | tee /tmp/alembic-before.txt

# 2. code — fast-forward only, as the repo owner
sudo -u icb git -C /opt/icb-platform fetch origin
sudo -u icb git -C /opt/icb-platform merge --ff-only origin/backport/v1.39-base
git -C /opt/icb-platform log --oneline -1

# 3. DB migration 0038 -> 0039 (additive, guarded, idempotent)
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic upgrade head'
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic current'

# 4. rebuild the SPA bundle (required — frontend/src changed)
sudo -u icb bash -lc 'cd /opt/icb-platform/frontend && npm run build'

# 5. restart the service
sudo systemctl restart icb-backend
sleep 6
systemctl is-active icb-backend
systemctl show icb-backend -p ActiveEnterTimestamp --no-pager

# 6. boot must be clean — expect 4 workers, zero "BOOTSTRAP FAILED"
sudo journalctl -u icb-backend --since '-2 min' --no-pager | grep -Ec 'Application startup complete'
sudo journalctl -u icb-backend --since '-2 min' --no-pager | grep -c 'BOOTSTRAP FAILED' || echo '0 bootstrap failures'

# 7. smoke
curl -k -s https://127.0.0.1/health; echo
```

Expected: step 6 prints **4** startup-complete lines and **0** bootstrap failures;
step 7 prints `{"status":"ok"}`.

> `sudo journalctl` — not bare `journalctl`. The `icb` account is not in `adm`;
> `mickeyger` is, but the sudo form is what has worked on this box.

## Rollback

Additive migration, so code-only rollback is usually enough — the new table simply goes
unused.

```bash
# code only (leaves 0039 in place, harmless)
sudo -u icb git -C /opt/icb-platform checkout f4b1e1d
sudo -u icb bash -lc 'cd /opt/icb-platform/frontend && npm run build'
sudo systemctl restart icb-backend
```

Full rollback including the schema, if ever needed:

```bash
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic downgrade 0038'
```

`downgrade 0038` drops `validated_references` — **any references Nadie has created would be
lost**, so prefer the code-only rollback unless the table itself is the problem.

## Post-deploy verification (CA, from outside)

1. `GET /health` → 200.
2. `GET /login` carries `style.css?v=17`; the calculator page carries `calculator.js?v=155`.
3. `/api/validated-references/settings` → 401 unauthenticated (route exists and is gated).
4. `costings.validated_refs_manage` granted to `{admin, full}` — read the actual
   `role_permissions` rows.
5. Calculator: compact parameter rows, no Print / Full Report, Total Cost on one line.
6. `validated_references` table present with its three indexes; tolerance row = 2.

## User-visible change to mention to Nadie

The costings calculator's left panel is **denser** (captions beside their fields) and the
summary panel has lost **Print**, **Full Report** and the **Selling Price** line — the
category totals get that space back. Nothing about pricing, saving or quote numbering
changed.
