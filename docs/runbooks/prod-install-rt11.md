# RT11 — WeasyPrint on prod for the letterhead quote: the install steps of the release window

**For the release CA (D1)** and Michael's window, after Burt's answers on the fixed text are in the templates and
Marnus has answered on the apt package (RT11_RULING_1). This runbook covers only WeasyPrint's steps; the release's own
runbook (VERSION, tag, `release.sh deploy`, the three-door probe) wraps them.

**The order matters, and the kit enforces it (G1):**
1. the release deploys the RT11 code (it carries the shipped Liberation faces) — on that code the gate still reads
   False, because WeasyPrint is not installed: prod keeps showing "Official quotes are issued from SAP.";
2. **apt** (`libharfbuzz-subset0` 8.3.0-2build2, the one package; nothing upgraded) — or Group IT runs it;
3. **pip** (the lock's 10 packages, as the venv owner) — it refuses before step 1 or step 2;
4. restart `icb-backend` (the release's restart): the workers read the gate at start-up;
5. **verify** — the five quote templates rendered with the deployed code, faces Liberation, the gate True;
6. the release's three-door probe; a results page shows "Generate Quote".

**Rollback:** `rollback` uninstalls the lock and removes the apt package; restart `icb-backend`; the gate reads False and
the SAP line returns. The code needs no rollback for this.

Kit: `ops/prod-rt11/install/` (`rt11_install.sh`, `rt11_verify.py`, `weasyprint-lock.txt`, `rt11_install_vm.sh`,
`run_install.ps1`, `mkstage_install.sh`), staged by
`bash ops/prod-rt11/install/mkstage_install.sh C:/Users/micge/Documents/icb-rt11-stage/install <release commit>` from a
commit that is on origin (the release CA passes the release tag's commit). Tests: `backend/tests/test_ops_rt11.py`.
Sims: `ops/prod-rt11/install/sim/` — the WSL scenarios in the Ubuntu 24.04 clone of prod (real apt and pip) and the
Windows PowerShell 5.1 run of every block below. Each step's report lands in Downloads; prod `/tmp` is read back clean.

## The steps

**1 — preflight (read only; any time outside the window)**

📋 PASTE INTO: PowerShell (your laptop)          ← or: Command Prompt
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt11-stage\install\run_install.ps1" preflight
```
FIRST LINE YOU SHOULD SEE: ######## RT11 install: preflight . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - preflight (read only). Report: … → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; paste it back to me

**2 — apt (in the window, after the code is deployed)**

📋 PASTE INTO: PowerShell (your laptop)          ← or: Command Prompt
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt11-stage\install\run_install.ps1" apt
```
FIRST LINE YOU SHOULD SEE: ######## RT11 install: apt . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - apt (it changes prod). Report: … → copy the whole window and paste it back to me
IF YOU SEE "STOP": its STOP line says what was and was not changed; paste it back to me

**3 — pip (in the window, after step 2)**

📋 PASTE INTO: PowerShell (your laptop)          ← or: Command Prompt
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt11-stage\install\run_install.ps1" pip
```
FIRST LINE YOU SHOULD SEE: ######## RT11 install: pip . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - pip (it changes prod). Report: … → copy the whole window and paste it back to me
IF YOU SEE "STOP": its STOP line says what was and was not changed; paste it back to me

**4 — verify (read only; after the restart)**

📋 PASTE INTO: PowerShell (your laptop)          ← or: Command Prompt
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt11-stage\install\run_install.ps1" verify
```
FIRST LINE YOU SHOULD SEE: ######## RT11 install: verify . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - verify (read only). Report: … → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; paste it back to me

**5 — rollback (only if the CA asks for it)**

📋 PASTE INTO: PowerShell (your laptop)          ← or: Command Prompt
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt11-stage\install\run_install.ps1" rollback
```
FIRST LINE YOU SHOULD SEE: ######## RT11 install: rollback . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - rollback (it changes prod). Report: … → copy the whole window and paste it back to me
IF YOU SEE "STOP": its STOP line says what was and was not changed; paste it back to me
