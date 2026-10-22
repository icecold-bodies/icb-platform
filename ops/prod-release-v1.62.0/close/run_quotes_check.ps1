# RT9 close (RT9_RETURN_1b Q1) - which costings were saved during the v1.62.0 window? READ ONLY. ONE line, from
# PowerShell OR Command Prompt:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\close\run_quotes_check.ps1"
#
# Copies the one kit (icb-rt9-quotes) to prod /tmp, unpacks, verifies and stamps it there (rt9_vm.sh, run by path),
# then runs it BY PATH under sudo over ssh -t (sudo asks for the VM password; nothing shows while you type). The
# output is NOT piped: sudo needs the terminal. Filled in by mkstage_close.sh: __QKIT__ (and window_common.ps1's).
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'window_common.ps1')
$name, $want = '__QKIT__'.Split(':')

Enter-Window 'quotes check (read only)'
$tar = Join-Path $Here "$name.tar"
if (-not (Test-Path $tar)) { Stop-Step KIT "no $tar - re-stage" }
$sha = (Get-FileHash -Algorithm SHA256 $tar).Hash.ToLower()
if ($sha -ne $want) { Stop-Step KIT "$name.tar sha256 is $sha, the stage wrote $want - re-stage" }
Write-Host "== kit ok: $name.tar sha256 $($sha.Substring(0,12))..."
& scp -q -o BatchMode=yes $tar "${Vm}:/tmp/"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "scp failed (exit $LASTEXITCODE)" "nothing ran on prod. Paste the same line again." }
& ssh -o BatchMode=yes $Vm "bash /tmp/icb-rt9-vm.sh unpack $name"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "the kit did not unpack cleanly on prod (exit $LASTEXITCODE)" }
Write-Host "== on prod: sudo bash /tmp/icb-rt9-quotes/rt9_quotes.sh"
Write-Host "== sudo asks for the VM password next; nothing shows while you type. Then wait for the ######## line."
& ssh -t -o BatchMode=yes -o ConnectTimeout=10 $Vm 'sudo bash /tmp/icb-rt9-quotes/rt9_quotes.sh'
$rc = $LASTEXITCODE
Write-Host ""
if ($rc -eq 0) {
  Write-Host "######## DONE - the quotes check ended with exit 0. Copy the whole window and paste it back to the CA."
  exit 0
}
Stop-Step QUOTES "the quotes check ended with exit $rc - read the STOP line above" "it is read only: nothing was changed. Copy the whole window and paste it back to the CA."
