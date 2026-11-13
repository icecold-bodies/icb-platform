# RT11 §3.0 — the read-only prod check for the letterhead quote (WeasyPrint)

**What it answers, before anything is installed:** what would "Generate Quote" (the MES letterhead quote,
`/results/{id}/report`: HTML templates → WeasyPrint → PDF) need on prod, and who could press it?

It reports, read only:
- the Ubuntu release, the kernel and the architecture;
- the deployed venv's python and pip, and whether `weasyprint` imports today;
- the system libraries WeasyPrint needs (Pango, HarfBuzz and its subsetter, fontconfig) and the fonts installed, with
  what fontconfig hands back for Arial, sans-serif and monospace;
- `apt-get -s install --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`: a **simulation**
  on the package lists as they are (no `apt-get update`, no lock): what would be newly installed, and whether anything
  would be upgraded;
- `pip install --dry-run` of the base requirements plus `weasyprint==70.0` with the deployed venv's python, run as
  `nobody` (who cannot write the venv) with no cache: what would be installed, and whether an installed package changes;
- who holds `quote.generate`: the roles granted it and the number of users per role, and the per-user overrides —
  role names and counts only; admin is a wildcard in code;
- the letterhead templates, the body families and body types they serve, and the live body costings per template.

No names (G4): role names, counts, template slugs and body-type names only. Every database session is read-only. No
service is touched; nothing under `/opt/icb-platform` changes. The check removes its own kit when it ends, and the line
reads back that prod `/tmp` holds nothing of it.

Kit: `ops/prod-rt11/` (`rt11_check.sh`, `rt11_vm.sh`, `run_check.ps1`, `mkstage_check.sh`), staged by
`bash ops/prod-rt11/mkstage_check.sh C:/Users/micge/Documents/icb-rt11-stage/check <commit>` from a commit that is on
origin. Tests: `backend/tests/test_ops_rt11.py` (every SELECT run on the test database in a read-only session). Sims:
`ops/prod-rt11/sim/` — the WSL scenarios run in an Ubuntu 24.04 clone of prod (real apt-get, dpkg, fontconfig and
pip), and the Windows PowerShell 5.1 run of the block below.

## The one step

Run it at any time: it reads only. VPN on if you are off the LAN.

**1 — the check**

📋 PASTE INTO: PowerShell (your laptop)          ← or: Command Prompt
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt11-stage\check\run_check.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT11 prod check (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head a29db35 …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - read only. Report: … → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; paste it back to me
