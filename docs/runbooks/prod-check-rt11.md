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

## OUTCOME (23 Oct 2026, 12:17 SAST)

- **The run:** Michael's paste.
  - `icb-mes-prod`, database `icb_platform @ 127.0.0.1:5432`, head `a29db35` (v1.62.0), alembic `0053`, boot
    2026-10-11 08:02:53. Every session read-only.
  - The kit was staged from `3eb8def`.
  - **DONE (read only).** Prod `/tmp` read back clean: the kit, the tar, the report and the helper were all absent.
    Nothing was changed on prod.
- **The report:** `docs/audit/rt11_2026-10/prod/rt11-check-20261023-121804.txt` (78 lines), sha256 `6e8ca8781be661a2…`.
  It is byte-identical to the file the line fetched. It holds versions, package names, role names, counts, template
  slugs and body-type names only (G4).
- **The answer** (RT11_RETURN_1b; built in #232, ruled in RT11_RULING_1 and RT11_RULING_2):
  - Ubuntu 24.04.4, Python 3.12.3, pip 26.1.2; `weasyprint` absent.
  - Pango 1.52.1 and HarfBuzz 8.3.0 are already installed. `apt-get -s` shows **1 new package**
    (`libharfbuzz-subset0` 8.3.0-2build2) and **0 upgraded**.
  - `pip --dry-run` shows **10 new, 0 changed**. These are exactly the 10 versions in the install kit's
    `weasyprint-lock.txt`.
  - Fonts: DejaVu only, and **Arial → DejaVu Sans**. That made RULING_1's Q1 certain: ship Liberation Sans and Mono
    with `@font-face`.
  - `quote.generate`: admin 4, full 3, user 1 (8 users by role). Planner and sales do not hold it. No per-user
    overrides.
  - 9 of 16 active bodies have a template. Chiller, ice cream and Manni have none: 22 of the 54 body quotes in the last
    90 days. 0 live body costings carry a discount.
- **One line printed `tee: /tmp/icb-rt11-check-report.txt: Permission denied`:**
  - Prod's `fs.protected_regular=2` refuses even root an O_CREAT open of a file another user owns in the sticky
    `/tmp`. The kit appended its closing line after handing the report to the sudo user.
  - The result, the fetched report and the cleanup were unaffected. Only that last line is missing from the report.
  - **Fixed in RT11's build** (`dccbe1e`, in #232): the line is written before the `chown`.
  - The sim is prod-like: a sticky 1777 `/tmp`, sudo user `mickeyger` (uid 1500) and `fs.protected_regular=2`. It
    fails on the 23 Oct ending and passes on the fix.
  - `test_ops_rt11.py` refuses any write to the report after its `chown`, with a negative control.
- **The stage folder** `Documents\icb-rt11-stage\check` was removed on 14 Nov (RULING_2). To run the check again,
  restage it with `bash ops/prod-rt11/mkstage_check.sh C:/Users/micge/Documents/icb-rt11-stage/check <commit>`.
