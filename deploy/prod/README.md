# Production deploy scripts

Deploying the ICB MES to `https://192.168.0.251/mes-app/`.

Until now every release was a hand-written runbook with a paste-this block, and the
migration / rebuild / restart decisions were re-derived by hand each time. Those decisions
are mechanical — they fall out of diffing the deployed commit against the target — so they
live in `icb-deploy.sh` now. The per-release runbooks in `docs/runbooks/` remain the record
of *what a release contains and why*; this is the *how*.

## From Windows (normal case)

```powershell
cd deploy\prod
.\Push-ToProd.ps1 -Status          # what is on prod right now
.\Push-ToProd.ps1 v1.48.1 -DryRun  # the plan, without touching anything
.\Push-ToProd.ps1 v1.48.1          # deploy (asks on the VM before changing anything)
```

`Push-ToProd.ps1` sends the shell script over ssh each run, so **you are always running the
version in your working copy** — prod does not need to have pulled it first. It allocates a
TTY so `sudo` can prompt.

## On the VM

If you are already sitting on the box:

```bash
cd /opt/icb-platform/deploy/prod
./icb-status.sh --with-db
./icb-deploy.sh v1.48.1 --dry-run
./icb-deploy.sh v1.48.1
```

## What the deploy script decides for you

By diffing the deployed commit against the target:

| Step | Runs when |
|---|---|
| **DB backup** | a migration is about to run |
| **`alembic upgrade head`** | a new file appears in `backend/alembic/versions/` |
| **`npm run build`** | anything under `frontend/` changed |
| **`systemctl restart`** | backend Python changed, or a migration ran |

The restart rule is the interesting one: **templates and static assets reload from disk**, so
a template/CSS-only release genuinely needs no restart — that is how v1.46.4 went out. Force
one with `--force-restart` if you want it anyway.

It also warns, without deciding for you, when `requirements*.txt` / `package.json` change (you
may need an install first) or when `.env.example` changes (prod's `.env` is Marnus-owned —
**append missing keys, never overwrite**).

## Safety properties

- **Refuses anything that is not a fast-forward.** Going backwards is `icb-rollback.sh`.
- **Refuses to deploy over a dirty tree** — but only counts *tracked* modifications. Prod has
  ~350 untracked build droppings (`.npm-cache/`, `__pycache__`); those are ignored.
- **Verifies by SHA, never by `git describe`.** `0dd4075` carries both `v1.47.2` and `v1.48.0`,
  so describe names a tag you did not ask for. `icb-status.sh` prints *every* tag on the
  deployed commit for the same reason.
- **Confirms the restart actually took** by comparing `ActiveEnterTimestamp` before and after.
  `systemctl is-active` alone reports a stale process as healthy.
- **Fails on `BOOTSTRAP FAILED`** in the boot log — that is the multi-worker permission-seeding
  race, and a worker that hit it has silently lost its role grants.
- **Never runs `alembic downgrade`.** Migrations here are additive, so old code ignores them;
  downgrading destroys data (0042's downgrade deletes the repair-document counter series and
  any numbers issued from it). Rollback is code-only, by design.
- Prints the exact rollback command, with the pre-deploy SHA, when it finishes.

## Rollback

```powershell
.\Push-ToProd.ps1 -Rollback 0dd4075
```

Resets the code, rebuilds the SPA if that range touched `frontend/`, restarts, verifies.
It refuses to "roll back" to something *ahead* of what is deployed.

## Why this cannot run unattended

`/opt/icb-platform` is owned by `icb`, `mickeyger` is not in that group, and `mickeyger`'s
sudo is password-required. The scripts ask for the password once, up front, with a message
saying why — rather than letting a bare prompt appear mid-run and look like a hang. There is
deliberately no way to supply it non-interactively.

## Facts these scripts assume

| | |
|---|---|
| Repo | `/opt/icb-platform`, owned `icb:icb`, branch `backport/v1.39-base` |
| Venv | `/opt/icb-platform/.venv` — at the **repo root**, not under `backend/` |
| Env | `/etc/icb/backend.env` — root-gated, hence `sudo` for every alembic call |
| Service | `icb-backend`, `uvicorn --workers 4` |
| Backup | `icb-pg-backup.service`, nightly ~02:30 |
| Health | `https://127.0.0.1/health` — self-signed cert, so `curl -k` |
| Journal | `sudo journalctl` — `icb` is not in `adm` |
