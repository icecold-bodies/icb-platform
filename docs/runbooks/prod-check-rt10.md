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
