# Prod deploy: v1.59.0 "Admin → Costing audit" + the v1.57 audit tool (tag v1.59.0)

Target: **`https://192.168.0.251/mes-app/`** and **`https://mes.icecoldgrp.online`** · repo `/opt/icb-platform`
· service `icb-backend` (`uvicorn --workers 4`) · DB `icb_platform` · BA dispatch 4 (release ops only).

| | |
|---|---|
| Prod is at | **`6b77d52`** (#190 v1.56, deployed 16 Sep 10:52 SAST), alembic **0048** |
| Deploy to | **the merge commit of the release PR** that carries this runbook. It is recorded by `mkstage.sh` in `expected.env` and in the OUTCOME below. |
| Range | `6b77d52..<target>`: #191–#194 (the audit CLI, packs, golden, CI, docs), **#195 v1.59 page `a5238b8`**, #196 (CI baseline = prod), #197 (v1.58 pricing corrections: tool, records, snapshot; the data was applied on prod 28 Sep 13:16), `59ea9bb` (BA docs), and the release PR (this runbook, the kit, `backend/VERSION`) |
| DB migration | **YES, exactly one:** `0049_costing_audit_runs` (a new table plus 2 indexes; inspector-guarded, additive; up→down→up proven on dev by the build lane) |
| Frontend rebuild | **NO.** `frontend/` is untouched in the range (asserted by the kit's guard); the served SPA bundle must stay byte-identical |
| Service restart | **YES.** 4 backend `.py` files (`database.py`, `main.py`, `routers/costing_audit.py`, `services/costing_audit_runs.py`) and the migration |
| Templates | `base.html` (the menu entry) and `admin_costing_audit.html`: they reload from disk |
| New dependency | **PyYAML 6.0.2** (`requirements.txt`). Installed into `/opt/icb-platform/.venv` by the kit if absent (`--no-deps`; PyYAML has none), before the code moves |
| Env / `.env` | none |
| Cache-busts | none: `calculator.js?v=182` and `style.css` are unchanged, and no static file changed in the range |
| Data | none. The migration creates an empty table; the permission `admin.costing_audit` is seeded by the boot-time bootstrap and granted to `admin` |

## Why

The costing audit (v1.57) could only run from a terminal or a VM paste. v1.59 puts it in the app, under **Admin →
Costing audit**. An admin picks a pack and runs it, and on prod it audits prod. The page reads the report, the
history and "changed since the previous run" from the new `costing_audit_runs` table. The run is read-only against
pricing: the probe costs on a `default_transaction_read_only` connection and rolls back.

## The kit (committed with this runbook, staged byte-exact)

`ops/prod-release-v1.59.0/`:
- `release.sh` runs on the VM, in three modes.
- `mkstage.sh` builds the staging folder from committed blobs and derives every expected value from the target tree:
  - the target and previous SHA;
  - the alembic before/after;
  - the one new migration;
  - the changed-file count and C-sorted sha256;
  - `calculator.js?v=` and its blob sha256;
  - the 6 new OpenAPI paths;
  - the PyYAML pin and the permission key.

Every real outcome is its own assert with a **named STOP** (`KIT`, `DB`, `ANCHORS`, `BYTES_BEFORE`, `PYYAML`,
`BACKUP`, `GUARD`, `DRYRUN`, `DEPLOY`, `RESTART`, `RECORD`, `TRACEBACKS`, and each post-check by name). Decorative
pipelines carry `|| true`. There is no bare `set -e` (the 22 Aug lesson: `systemctl status` on a finished oneshot
exits 3).

**Proved before use** in a WSL simulation. Prod's paths were bind-mounted from a scratch folder in a private mount
namespace; the **real `deploy/prod/icb-deploy.sh` from `6b77d52`** ran against stubbed systemd, postgres, curl, sudo
and pip. Results:

| scenario | result |
|---|---|
| happy path | preflight PASS → verify fails on exactly the 11 not-yet-deployed checks → deploy DEPLOYED → verify 0 failures → deploy again = "ALREADY DEPLOYED", verify only. No root-owned `__pycache__` left in the repo. |
| pip cannot install | `STOP [PYYAML]` before the backup; nothing changed |
| a worker logs BOOTSTRAP FAILED | `icb-deploy.sh` fails → `STOP [DEPLOY]` naming the rollback anchor and the backup |
| a traceback after the restart | `STOP [TRACEBACKS]` |
| prod moved by hand | `STOP [ANCHORS]` before anything |

## Sequence

**0. Michael picks the window.** The migration and the restart mean a short outage on all four workers, a few
seconds for the restart. Nadie's and Lezette's quoting hours are the constraint. Nothing changes on prod before
the window.

**1. The CA stages the kit** after the release PR merges:

```
bash ops/prod-release-v1.59.0/mkstage.sh <empty-dir> <merge-sha>
scp <empty-dir>/icb-release-v1.59.0.tar icb@192.168.0.251:/tmp/
ssh icb@192.168.0.251 'cd /tmp && tar -xf icb-release-v1.59.0.tar'
```

The CA verifies `SHA256SUMS` and the CR count (0) on the VM.

**2. Preflight (read-only), any time before the window.** Michael, on the VM (after `ssh mickeyger@192.168.0.251`):

```
sudo bash /tmp/icb-release-v1.59.0/release.sh preflight
```

It asserts:
- the database is `icb_platform`, alembic `0048`, HEAD `6b77d52`, and there are no tracked modifications;
- `calculator.js?v=182` on `127.0.0.1` and the LAN equals the target-tree blob;
- the SPA bundle named in `dist/index.html` is served byte-identical to disk on both doors;
- health is 200;
- the backup directory is writable;
- `deploy/prod/icb-deploy.sh` is present, and `icb`'s sudo is NOPASSWD.

It reports:
- `import yaml` and `pip install --dry-run PyYAML==6.0.2` (so the install is a planned step, not a surprise);
- `pip --dry-run -r requirements.txt`, for information only;
- free space and the latest backups.

Then the known-hit check, still read-only: `sudo bash /tmp/icb-release-v1.59.0/release.sh verify` **must fail on
exactly** HEAD, ALEMBIC, TABLE, INDEXES, PERMISSION, ADMIN_GRANT, the two OpenAPI checks, PAGE_UNAUTH and API_UNAUTH
(404 before the deploy), plus PYYAML if it is absent. It must pass the rest. That proves each check can see what it is
meant to see.

**3.–8. Deploy, in the window.** Michael, on the VM:

```
sudo bash /tmp/icb-release-v1.59.0/release.sh deploy
```

(From Windows instead: `ssh -t mickeyger@192.168.0.251 "sudo bash /tmp/icb-release-v1.59.0/release.sh deploy"`.
`-t` gives sudo its password prompt; do not pipe it.)

| step | what | asserted |
|---|---|---|
| 1 anchors | start state | HEAD `6b77d52` + alembic 0048 (fresh), or HEAD = target (resume / already deployed); no tracked modifications; rollback anchor written |
| 2 bytes before | the served baseline | `calculator.js?v=182` = the target blob on both doors; SPA served = disk |
| 3 PyYAML | install if absent | `import yaml` = 6.0.2 afterwards (installed as the venv owner, `--no-deps`) |
| 4 **backup** | `pg_dump -Fc icb_platform` → `/var/backups/postgres/icb_platform_pre-v1.59.0_<ts>.dump` (mode 600) | exists, size > 0, sha256 printed, `pg_restore --list` has TABLE DATA including `alembic_version`. **This is the rollback for 0049.** |
| 5 fetch + guard | `git fetch origin --tags` as icb | `origin/backport/v1.39-base` = the staged target; `6b77d52` is an ancestor; the changed-file count **and** C-sorted sha256 equal the staged values; the new migrations are exactly `0049_costing_audit_runs.py`; `frontend/` untouched → **no SPA rebuild** |
| 6 dry run | `deploy/prod/icb-deploy.sh <target> --dry-run` as icb | plan = "DB migration YES - 0049", "SPA rebuild no", "Service restart YES" |
| 7 deploy | `icb-deploy.sh <target> --yes` as icb (the 15–16 Sep precedent): its own backup service run, ff-only, `alembic upgrade head`, restart, health | exit 0 and "DEPLOYED"; MainPID changed; `/var/tmp/icb-deploy-state` = `completed <target>` |
| 8 post-deploy | after 20 s | HEAD = target; alembic **0049**; table + 2 indexes; `admin.costing_audit` seeded + granted to admin; active; **exactly 4** "Application startup complete" since the restart; **0** BOOTSTRAP FAILED; **0** tracebacks; health 200; PyYAML 6.0.2; the tool imports; `/openapi.json` on `127.0.0.1` **and** the LAN lists all 6 new paths and is byte-identical across both; unauthenticated `/admin/costing-audit` → 30x/401/403 (never 200, never 404); `/api/admin/costing-audit/runs` → 401/403; `calculator.js` and the SPA unchanged on both doors |

Everything is logged under `/tmp/icb-release-v1.59.0/out-<mode>-<ts>/` (`run.log`, the `icb-deploy.sh` outputs,
`OUTCOME.txt`). The CA fetches it.

**9. The third door: Cloudflare, by the CA from outside, only once the disk matches** (the 14 Sep lesson: a CF
probe before the deploy caches old bytes under a new URL).
- `https://mes.icecoldgrp.online/openapi.json` has the 6 paths, and its bytes equal the LAN door's.
- `calculator.js?v=182` and the SPA bundle are byte-identical to the LAN door.

No cache purge unless this fails, and then only after the BA has reviewed the purge step.

**10. Acceptance: the page works on prod.** Michael, on **the domain**:

| check | expected |
|---|---|
| `/admin/costing-audit` signed out | redirected to login or 403, never the page (also asserted in step 8) |
| permission | `admin.costing_audit` seeded, granted to admin (asserted in step 8) |
| run **smoke** | completes; the report renders; a history row is written; the HTML/CSV downloads work. The header reads **Production** · `accepted_differences.prod.yaml` |
| run **chillers** | **0 unaccepted.** The counts equal the latest committed prod reference run (`docs/audit/costing_audit/2026-09/prod/`, 28 Sep 13:45, post-apply): **pass 981 · flag 0 · accepted 76 · unverifiable 0** (skip 196; 98 scenarios). The page and the CLI read the same data through the same engine: **any difference is a page bug. Report the cells, change nothing.** |
| smoke's expected counts | **pass 156 · flag 0 · accepted 33 · unverifiable 9** (skip 36) |
| re-run **smoke** | "No change since <the first run>" |

**11. Tag v1.59.0** (annotated) on the deployed commit. The first tag since v1.50.0, so its message names what it
consolidates: v1.51 foam/tips · v1.52 September prices + capture-for-user · v1.53 configurator arc · v1.53.1 ·
v1.54 BOM order · v1.55 Enter walk · v1.56 parameters · v1.57 costing audit · v1.58 audit pricing corrections ·
v1.59 audit admin page. Proof: the local tag-object SHA equals `git ls-remote --tags origin v1.59.0`, byte for byte
(D2); `git rev-list -n 1 v1.59.0` = the deployed commit.

**Version shown in the app:** `_app_version()` prefers `git describe --tags --abbrev=0` and falls back to
`backend/VERSION`, and it is read once at startup. Before this release `backend/VERSION` read **`v1.40.0`**; the
release PR bumps it to **`v1.59.0`**. Prod's footer shows `v1.50.0` until the first restart after the tag reaches
prod's repo (the deploy's fetch runs before the tag exists).

**12. Housekeeping.** `/tmp/icb-release-v1.59.0` stays until the OUTCOME is committed. (`/tmp/icb-audit*`: the v1.58
lane already removed them on 28 Sep with Michael's paste, after that lane's final snapshot; the next VM audit paste
re-stages its copy and PyYAML.)

## Rollback (decided before the run)

- **Code:** back to `6b77d52` and restart. Either `sudo -u icb bash /opt/icb-platform/deploy/prod/icb-rollback.sh
  6b77d52`, or directly:
  - `sudo -u icb git -C /opt/icb-platform reset --hard 6b77d52`
  - `sudo systemctl restart icb-backend`

  Then re-probe all three doors. No SPA rebuild is needed (frontend untouched).
- **Migration:** `6b77d52` does not know `costing_audit_runs`, so leaving 0049 in place is harmless. To remove it:
  `sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; cd /opt/icb-platform/backend && /opt/icb-platform/.venv/bin/alembic downgrade 0048'`.
  It drops the table and its run history; it was tested up→down→up on dev by the build lane. Otherwise, restore the
  step-4 backup with `pg_restore`.
- **PyYAML** stays installed; it is harmless to `6b77d52`.
- **Anchor:** `6b77d52` · backup named in the OUTCOME.

**After a STOP:**
- Before step 7, nothing on prod has changed except possibly PyYAML.
- From step 7 on, re-running `release.sh deploy` resumes: at the target with no completion record, `icb-deploy.sh`
  re-runs migrate and restart, both idempotent. Every assert runs again.
- A `BOOTSTRAP FAILED` is the known worker race; one more restart normally heals it.
- If the page itself is broken, roll back the code.

## OUTCOME

*(appended after the run)*
