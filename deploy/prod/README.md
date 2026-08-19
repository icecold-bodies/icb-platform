# Production deploy scripts

Deploying the ICB MES to `https://192.168.0.251/mes-app/`.

Until now every release was a hand-written runbook with a paste-this block, and the
migration / rebuild / restart decisions were re-derived by hand each time. Those decisions
are mechanical — they fall out of diffing the deployed commit against the target — so they
live in `icb-deploy.sh` now. The per-release runbooks in `docs/runbooks/` remain the record
of *what a release contains and why*; this is the *how*.

## From Windows (normal case)

Scripts do not run by name on this machine: PowerShell's execution policy is the Windows
default (**Restricted** - every scope reads `Undefined`), so `.\Push-ToProd.ps1` fails with
"running scripts is disabled on this system", and cmd.exe cannot run a `.ps1` at all -
typing it there does nothing, silently.

So use the shim, which carries a per-process bypass and changes no machine setting. **It
works from cmd.exe and from PowerShell:**

    cd C:\Users\micge\Documents\icb-platform\deploy\prod
    push-to-prod.cmd -Status
    push-to-prod.cmd v1.49.1 -DryRun
    push-to-prod.cmd v1.49.1

In PowerShell write `.\push-to-prod.cmd` - PowerShell will not run a command from the
current directory without the `.\`. cmd.exe does not need it.

The long form, if you would rather not use the shim - also valid in both shells:

    powershell -NoProfile -ExecutionPolicy Bypass -File Push-ToProd.ps1 v1.49.1 -DryRun

`-Status` and `-DryRun` are read-only, need no password, and are always safe to run first.

Do NOT join lines with `&&` in Windows PowerShell 5.1 - it is a parse error there
("The token '&&' is not a valid statement separator in this version"). Use separate lines,
or `;`. cmd.exe and pwsh 7 both accept `&&`, which is part of why it is worth avoiding: the
same line behaves three different ways on this one machine.

## On the VM

These are LINUX commands, to be run **after** `ssh icb-mes-prod`. Pasting them into a
Windows shell gives "'~' is not recognized" or "not recognized as the name of a cmdlet".

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

## Encoding: these files are ASCII on purpose

`Push-ToProd.ps1` and the three `.sh` files contain **no non-ASCII characters**, and must
not gain any. Windows PowerShell 5.1 reads a UTF-8 file **without a BOM as ANSI**, so a
single tick or em-dash mangles mid-string and the parser dies with "The string is missing
the terminator" — pointing at a line that looks perfectly fine, followed by a cascade of
bogus "missing closing }" errors. One tick in one `Write-Host` made this script unrunnable
in the shell it was written for, while passing every test under pwsh 7.

The shell scripts are ASCII for a related reason: their output is read in that same
console, where UTF-8 dashes arrive as mojibake exactly when the operator most needs to read
carefully.

Colour is emitted only when stdout is a terminal and `NO_COLOR` is unset, so a piped or
logged run carries no raw escape codes.

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
