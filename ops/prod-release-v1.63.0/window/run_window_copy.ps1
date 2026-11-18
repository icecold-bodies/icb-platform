# RT12 window, step 1 - copy the three staged kits (release, All, doors) to prod /tmp, unpack them there, check each
# kit's SHA256SUMS and stamp it (the reboot guard). ONE line, from PowerShell OR Command Prompt:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_copy.ps1"
#
# Writes only /tmp/icb-*.tar, /tmp/icb-*/, /tmp/icb-rt12-vm.sh and /tmp/icb-rt12-window.started on prod (all owned by
# the ssh user); runs nothing else there. No sudo, so no password. Filled in by mkstage_window.sh: __KITS__ (and
# window_common.ps1's placeholders).
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'window_common.ps1')
$Kits = '__KITS__'.Split(' ')

# RT12_RULING_1 (7): the laptop's C: drive swung between 1.7 and 24.6 GB free on 12-13 Nov. The window's lines write
# little (the fetch's tar, ~25 MB), but a full disk mid-window would stop a paste half-way: under 5 GB free, STOP before
# anything reaches prod. RT12_SIM_FREE_GB exists for the PowerShell 5.1 sim's negative control only.
$FreeGb = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
if ($env:RT12_SIM_FREE_GB) { $FreeGb = [double]$env:RT12_SIM_FREE_GB }
Write-Host "== C: free: $FreeGb GB (the window needs 5 GB or more)"
if ($FreeGb -lt 5) {
  Write-Host ""
  Write-Host "######## STOP [DISK]: C: has $FreeGb GB free; the window needs 5 GB or more. Nothing ran on prod. Free some space (your Downloads folder holds earlier window tars), then paste the same line again."
  exit 1
}

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
& scp -o BatchMode=yes -o ConnectTimeout=10 @tars "${Vm}:/tmp/" > $null
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "scp failed (exit $LASTEXITCODE) - its reason is in the lines above" "the copy did not finish; nothing ran on prod. Paste the same line again." }
& ssh -o BatchMode=yes $Vm "bash /tmp/icb-rt12-vm.sh unpack $($names -join ' ')"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "a kit did not unpack cleanly on prod (exit $LASTEXITCODE)" "nothing ran on prod. Copy the whole window and paste it back to the CA." }
Write-Host ""
Write-Host "######## DONE - step 1: the kits are in prod /tmp, verified and stamped (a reboot after this makes each one refuse: copy again). Copy the whole window and paste it back to the CA."
