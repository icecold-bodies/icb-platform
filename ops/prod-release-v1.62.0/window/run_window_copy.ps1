# RT9 window, step 1 - copy the three staged kits (release, All, doors) to prod /tmp, unpack them there, check each
# kit's SHA256SUMS and stamp it (the reboot guard). ONE line, from PowerShell OR Command Prompt:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_copy.ps1"
#
# Writes only /tmp/icb-*.tar, /tmp/icb-*/, /tmp/icb-rt9-vm.sh and /tmp/icb-rt9-window.started on prod; runs nothing else
# there. No sudo, so no password. Filled in by mkstage_window.sh: __KITS__ (and window_common.ps1's placeholders).
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'window_common.ps1')
$Kits = '__KITS__'.Split(' ')

Enter-Window 'copy (step 1)'
$names = @()
foreach ($k in $Kits) {
  $name, $want = $k.Split(':')
  $tar = Join-Path $Here "$name.tar"
  if (-not (Test-Path $tar)) { Stop-Step KIT "no $tar - re-stage" }
  $sha = (Get-FileHash -Algorithm SHA256 $tar).Hash.ToLower()
  if ($sha -ne $want) { Stop-Step KIT "$name.tar sha256 is $sha, the stage wrote $want - re-stage" }
  Write-Host "== kit ok: $name.tar sha256 $($sha.Substring(0,12))..."
  $names += $name
}
Write-Host "== copy the $($names.Count) kits to prod /tmp"
$tars = $names | ForEach-Object { Join-Path $Here "$_.tar" }
& scp -q -o BatchMode=yes @tars "${Vm}:/tmp/"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "scp failed (exit $LASTEXITCODE)" "the copy did not finish; nothing ran on prod. Paste the same line again." }
& ssh -o BatchMode=yes $Vm "bash /tmp/icb-rt9-vm.sh unpack $($names -join ' ')"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "a kit did not unpack cleanly on prod (exit $LASTEXITCODE)" "nothing ran on prod. Copy the whole window and paste it back to the CA." }
Write-Host ""
Write-Host "######## DONE - step 1: the kits are in prod /tmp, verified and stamped (a reboot after this makes each one refuse: copy again). Copy the whole window and paste it back to the CA."
