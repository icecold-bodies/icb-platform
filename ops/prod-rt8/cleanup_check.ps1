# RT8 close (RT8_RULING_2) - remove the frozen-quote check's residue from prod /tmp, BY EXACT NAME, then read back.
# The ONE line Michael runs, from PowerShell or Command Prompt (ASCII only):
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-platform\ops\prod-rt8\cleanup_check.ps1"
#
# What it removes (nothing else; a name that is already gone is reported as absent): the three result folders and
# their tars, the staging stamp, the kit folder and the kit tar. sudo asks for the VM password once. The first line
# the VM prints names the machine and refuses when it is not icb-mes-prod. Nothing under /opt is touched.
$ErrorActionPreference = 'Continue'
$Vm = 'mickeyger@192.168.0.251'
$remote = @'
sudo bash -c 'set -u; echo "######## RT8 cleanup (prod /tmp) . machine $(hostname -s) . $(date -Is)"; [ "$(hostname -s)" = icb-mes-prod ] || { echo "######## STOP [WHERE]: this is $(hostname -s), not icb-mes-prod - nothing removed"; exit 1; }; n=0; for p in /tmp/icb-rt8-check/out-20261020-184034 /tmp/icb-rt8-check/out-20261021-063911 /tmp/icb-rt8-check/out-20261021-063911.tar /tmp/icb-rt8-check/out-20261021-073537 /tmp/icb-rt8-check/out-20261021-073537.tar /tmp/icb-rt8-check/.staged_at /tmp/icb-rt8-check /tmp/icb-rt8-check.tar; do if [ -e "$p" ]; then rm -rf -- "$p" && echo "removed $p" && n=$((n+1)); else echo "absent  $p"; fi; done; echo "read-back: $(ls -d /tmp/icb-rt8-check* 2>/dev/null || echo "nothing named icb-rt8-check is left in /tmp")"; echo "######## DONE - $n removed"'
'@
& ssh -t $Vm $remote
if ($LASTEXITCODE -ne 0) { Write-Host "######## STOP: the VM side exited $LASTEXITCODE - tell the CA"; exit 1 }
