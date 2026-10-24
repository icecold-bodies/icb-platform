# RT10 — the read-only prod check of revisions (RT10_RULING_1 Q3 ii)

**What it answers, before any release:** has today's Costings list already accepted, declined or built a job from
the OLDEST revision of a quote when a newer one was clicked (`CostingsContext`'s quote → id map, RT10_RETURN_1
§4.2)? And what revisions does prod hold?

It reports, read only:
- every quote number with 2+ rows: id, version (REV = version − 1), status, created and accepted times as stored,
  deleted yes / no, and the production job built from it (job id, created time);
- live duplicate versions;
- rows accepted while a newer live revision of the same quote existed;
- production jobs built from a revision that was not the latest live one when the job was created.

No names (G4): quote numbers, ids, versions, statuses and times only. Every database session is read-only. No service
is touched. The check removes its own kit when it ends, and the line reads back that prod `/tmp` holds nothing of it.

Kit: `ops/prod-rt10/` (`rt10_revisions.py`, `rt10_check.sh`, `rt10_vm.sh`, `run_check.ps1`, `mkstage_check.sh`),
staged by `bash ops/prod-rt10/mkstage_check.sh C:/Users/micge/Documents/icb-rt10-stage/check <commit>` from a commit
that is on origin. Tests: `backend/tests/test_ops_rt10.py`. Sims: `ops/prod-rt10/sim/` (WSL scenarios and the
Windows PowerShell 5.1 run of the block below).

## The one step

Run it at any time: it reads only. VPN on if you are off the LAN.

**1 — the check**

📋 PASTE INTO: PowerShell (your laptop)          ← or: Command Prompt
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt10-stage\check\run_check.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT10 prod check (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head a29db35 …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - read only. Report: … → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; paste it back to me

## OUTCOME (23 Oct 2026, 17:18 SAST)

- **The run:** Michael's paste.
  - Laptop `LAPTOP-DGJ0U6RQ` → `icb-mes-prod`, head `a29db35` (v1.62.0), boot 2026-10-11 08:02:53.
  - The kit was staged from `9345d87` (CI 7/7 green on that commit), tar sha256 `4cc413a9…`.
  - alembic `0053`, every session read-only, database time zone Africa/Johannesburg.
  - **DONE (read only).** Prod `/tmp` read back clean: kit, tar, report and helper all absent.
- **The report:** `docs/audit/rt10_2026-10/prod/rt10-check-20261023-171814.txt`, sha256 `b9e3efd04413e711…`. It is
  byte-identical to the file the line fetched and holds quote numbers, ids, versions, statuses and times only.
- **The answer** (RT10_RETURN_2b, ruled in RT10_RULING_3: "v1.63.0 may ship"):
  - 97 costings (82 live), 93 quote numbers;
  - **0** accepted while a newer live revision existed;
  - **0** jobs built from an older revision;
  - **0** live duplicate versions.
- **The 2 quote numbers with 2+ rows:**

  | Quote | Rows |
  |---|---|
  | N10021/10/2026 | id 129 (REV 0) and id 135 (REV 1, saved 22 Oct 17:09), both live and pending |
  | N10022/10/2026 | id 130 (the 19 Oct REV 0) and ids 131–133, **all deleted**. 130 was live at RT9's 22 Oct 15:20 read-back; the BA asked Michael about it |

- **One line printed `tee: /tmp/icb-rt10-check-report.txt: Permission denied`:**
  - prod's `fs.protected_regular=2` refuses even root an O_CREAT open of a file another user owns in the sticky
    `/tmp`, and the kit appended its last information line after handing the report to the sudo user;
  - the result, the fetched report and the cleanup were unaffected; only that last line was missing from the report.
  - **Fixed in RT10's close:** the line is now written before the `chown`. The sim is now prod-like, with a sticky
    1777 `/tmp`, sudo user `mickeyger` (uid 1500) and the kernel's `fs.protected_regular=2`, and asserts the last line
    reaches the report. It fails on the 23 Oct kit and passes on the fix. `test_ops_rt10.py` refuses any write to the
    report after its `chown`, with a negative control.
