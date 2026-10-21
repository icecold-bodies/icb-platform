# RT8 close (RT8_RULING_2) - remove the frozen-quote check's residue from prod /tmp, BY EXACT NAME, then read back.
# The ONE line Michael runs, from PowerShell or Command Prompt (ASCII only: Windows PowerShell 5.1 reads a BOM-less
# file as ANSI):
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-platform\ops\prod-rt8\cleanup_check.ps1"
#
# It writes the small bash script below to a temp file (LF, no BOM), copies it to prod /tmp, runs it there over
# `ssh -t` (sudo asks for the VM password once), and reads /tmp back from here. The script names the machine first
# and refuses unless it is icb-mes-prod; it removes only the names listed (an absent name is reported, never guessed
# at); it deletes itself last. Nothing under /opt is touched.
#
# Why a file and not an inline command: the first version (21 Oct, 13:20) passed the script inline as one ssh
# argument with double quotes in it; Windows PowerShell 5.1 drops embedded double quotes when it hands an argument
# to a native command, so bash saw the banner's first '#' as the start of a comment and ran nothing (exit 0, one
# blank line). A file by path carries no quoting at all - the pattern every kit's run line already uses.
$ErrorActionPreference = 'Continue'   # native ssh / scp write to stderr; every exit code is checked by hand
$Vm     = 'mickeyger@192.168.0.251'
$Remote = '/tmp/icb-rt8-cleanup.sh'
function Stop-Step($tag, $why) { Write-Host ""; Write-Host "######## STOP [$tag]: $why"; Write-Host "######## tell the CA"; exit 1 }

$Body = @'
#!/usr/bin/env bash
# RT8 close - the frozen-quote check's residue, by exact name. Runs as root via sudo; deletes itself last.
set -u
echo "######## RT8 cleanup (prod /tmp) . machine $(hostname -s) . $(date -Is)"
[ "$(hostname -s)" = icb-mes-prod ] || { echo "######## STOP [WHERE]: this is $(hostname -s), not icb-mes-prod - nothing removed"; exit 1; }
n=0
names="/tmp/icb-rt8-check/out-20261020-184034
/tmp/icb-rt8-check/out-20261021-063911
/tmp/icb-rt8-check/out-20261021-063911.tar
/tmp/icb-rt8-check/out-20261021-073537
/tmp/icb-rt8-check/out-20261021-073537.tar
/tmp/icb-rt8-check/.staged_at
/tmp/icb-rt8-check
/tmp/icb-rt8-check.tar"
for p in $names; do
  if [ -e "$p" ]; then rm -rf -- "$p" && echo "removed $p" && n=$((n+1)); else echo "absent  $p"; fi
done
echo "read-back: $(ls -d /tmp/icb-rt8-check* 2>/dev/null || echo "nothing named icb-rt8-check is left in /tmp")"
echo "######## DONE - $n removed"
rm -f -- "$0"
'@

$Tmp = Join-Path $env:TEMP 'icb-rt8-cleanup.sh'
[IO.File]::WriteAllText($Tmp, (($Body -replace "`r`n", "`n").TrimEnd() + "`n"), (New-Object System.Text.UTF8Encoding($false)))
Write-Host "######## RT8 cleanup (prod /tmp) . machine $env:COMPUTERNAME -> $Vm . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "== copy the cleanup script to prod"
& scp -q -o BatchMode=yes $Tmp "${Vm}:$Remote"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "scp failed (exit $LASTEXITCODE) - nothing ran on prod" }
Write-Host "== run it on prod (sudo asks for your VM password)"
& ssh -t $Vm "sudo bash $Remote"
$rc = $LASTEXITCODE
if ($rc -ne 0) { Stop-Step RUN "the VM script stopped (exit $rc) - read its STOP line above" }
Write-Host "== read-back from here"
& ssh -o BatchMode=yes $Vm "ls -d /tmp/icb-rt8-check* $Remote 2>/dev/null || echo '   nothing named icb-rt8-check or icb-rt8-cleanup.sh is left in /tmp'"
Write-Host ""
Write-Host "######## DONE - tell the CA (paste this whole output)"
