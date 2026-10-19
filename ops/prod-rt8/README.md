# RT8 — the prod frozen-quote check (read only)

Can every pending quote on prod be edited at its saved prices (RT8_RULING_1, Q3)? Michael runs ONE line; nothing on
prod is written, no service is touched, and only allow-listed columns and keys are read (quote numbers, months,
body names, the stored lines' figures — never a customer, contact, user or description).

    powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt8-stage\check\run_check.ps1"

It copies the staged kit to prod `/tmp`, runs `rt8_frozen_check.sh` there over `ssh -t` (sudo asks for the VM
password), and fetches `Downloads\rt8-check-back-<ts>.tar`. The first line names the machine, database and HEAD and
refuses the wrong place; every database session is read-only (`PGOPTIONS`, asserted again inside the python).

| File | Role |
|---|---|
| `rt8_frozen_check.py` | the check: counts by month and body, the replay check per pending body quote (prod's own engine), repairs' stock lines, N10022/10/2026 named; allow-lists asserted at import |
| `rt8_frozen_check.sh` | the VM script: where-check, read-only sessions, env loaded silently, outputs + hashes + tar |
| `mkstage_check.sh` | stages the kit from a COMMIT (LF bytes, sha256-checked), fills `run_check.ps1` |
| `run_check.ps1` | Michael's one line |
| `sim/run_check_sim.sh` | the WSL simulation of the VM script (wrong machine, wrong db, tampered kit, not read-only, happy path) |

The allow-lists are pinned by `backend/tests/test_rt8_prod_kit_allowlist.py`, with a negative control.
