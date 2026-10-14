# RT6 window - copy the five staged kits to prod /tmp, unpack them there and verify each kit's SHA256SUMS. ONE line,
# from PowerShell OR Command Prompt (ASCII only: Windows PowerShell 5.1 reads a BOM-less file as ANSI):
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt6-stage\window\run_window_copy.ps1"
#
# The FIRST line names this machine, prod's machine and prod's HEAD; it refuses when they are not the expected ones
# (the VPN must be up). Writes only /tmp/icb-*.tar and /tmp/icb-*/ on prod; runs nothing else there.
# Filled in by mkstage_window.sh: __KITS__ __STAGED_FROM__ __EXPECT_HEADS__.
$ErrorActionPreference = 'Continue'   # native ssh / scp write to stderr; every exit code is checked by hand
$Here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kits   = '__KITS__'.Split(' ')
$Staged = '__STAGED_FROM__'
$Heads  = '__EXPECT_HEADS__'.Split(' ')
$Vm     = 'mickeyger@192.168.0.251'
$VmName = 'icb-mes-prod'
$PcName = 'LAPTOP-DGJ0U6RQ'
function Stop-Step($tag, $why) { Write-Host ""; Write-Host "######## STOP [$tag]: $why"; Write-Host "######## tell the CA"; exit 1 }

$errFile = [System.IO.Path]::GetTempFileName()
$probe = & ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm "hostname -s; git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD" 2>$errFile
$sshErr = ((Get-Content $errFile -ErrorAction SilentlyContinue) -join ' ').Trim()
Remove-Item $errFile -ErrorAction SilentlyContinue
$vmHost = if ($probe) { "$($probe[0])".Trim() } else { '?' }
$vmHead = if ($probe -and $probe.Count -gt 1) { "$($probe[1])".Trim() } else { '?' }
$short  = if ($vmHead.Length -ge 7) { $vmHead.Substring(0, 7) } else { $vmHead }
Write-Host "######## RT6 window copy . machine $env:COMPUTERNAME -> $vmHost . db icb_platform (checked by each kit on the VM) . head $short . stage $($Staged.Substring(0,7)) . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
if ($env:COMPUTERNAME -ne $PcName) { Stop-Step WHERE "this is $env:COMPUTERNAME; the stage lives on $PcName" }
if ($vmHost -ne $VmName) {
  $why = if ($sshErr -match 'timed out|No route|unreachable') { 'prod is not reachable on the LAN address - connect the VPN, then run this line again' } else { 'tell the CA' }
  Stop-Step WHERE "ssh $Vm reached '$vmHost', not $VmName. ssh said: $(if ($sshErr) { $sshErr } else { '(nothing)' }). $why"
}
if ($Heads -notcontains $vmHead) { Stop-Step WHERE "prod's code is $short, this window expects $(($Heads | ForEach-Object { $_.Substring(0,7) }) -join ' or ')" }

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
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "scp failed (exit $LASTEXITCODE)" }
foreach ($n in $names) {
  & ssh -o BatchMode=yes $Vm "cd /tmp && tar -xf $n.tar && cd $n && sha256sum -c --quiet SHA256SUMS && echo '   $n unpacked and verified on prod'"
  if ($LASTEXITCODE -ne 0) { Stop-Step COPY "$n did not unpack cleanly on prod (exit $LASTEXITCODE)" }
}
Write-Host ""
Write-Host "######## DONE - the five kits are in prod /tmp, verified. Next: the runbook's step 1 (All, pre)."
