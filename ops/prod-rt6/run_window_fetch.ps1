# RT6 window - bring every kit's out-* folder (the run records) back from prod /tmp to Downloads, in ONE tar. ONE
# line, from PowerShell OR Command Prompt (ASCII only):
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt6-stage\window\run_window_fetch.ps1"
#
# The FIRST line names this machine, prod's machine and prod's HEAD; it refuses a wrong place. Read only on prod except
# the one tar it writes in /tmp (the out-* folders are world-readable; nothing under /var/backups is read).
# Filled in by mkstage_window.sh: __KITS__ __STAGED_FROM__ __EXPECT_HEADS__.
$ErrorActionPreference = 'Continue'
$Kits   = '__KITS__'.Split(' ')
$Staged = '__STAGED_FROM__'
$Heads  = '__EXPECT_HEADS__'.Split(' ')
$Vm     = 'mickeyger@192.168.0.251'
$VmName = 'icb-mes-prod'
$PcName = 'LAPTOP-DGJ0U6RQ'
$Back   = Join-Path $env:USERPROFILE 'Downloads'
function Stop-Step($tag, $why) { Write-Host ""; Write-Host "######## STOP [$tag]: $why"; Write-Host "######## tell the CA"; exit 1 }

$errFile = [System.IO.Path]::GetTempFileName()
$probe = & ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm "hostname -s; git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD" 2>$errFile
$sshErr = ((Get-Content $errFile -ErrorAction SilentlyContinue) -join ' ').Trim()
Remove-Item $errFile -ErrorAction SilentlyContinue
$vmHost = if ($probe) { "$($probe[0])".Trim() } else { '?' }
$vmHead = if ($probe -and $probe.Count -gt 1) { "$($probe[1])".Trim() } else { '?' }
$short  = if ($vmHead.Length -ge 7) { $vmHead.Substring(0, 7) } else { $vmHead }
Write-Host "######## RT6 window fetch . machine $env:COMPUTERNAME -> $vmHost . db (none: files only) . head $short . stage $($Staged.Substring(0,7)) . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
if ($env:COMPUTERNAME -ne $PcName) { Stop-Step WHERE "this is $env:COMPUTERNAME; the stage lives on $PcName" }
if ($vmHost -ne $VmName) {
  $why = if ($sshErr -match 'timed out|No route|unreachable') { 'prod is not reachable on the LAN address - connect the VPN, then run this line again' } else { 'tell the CA' }
  Stop-Step WHERE "ssh $Vm reached '$vmHost', not $VmName. ssh said: $(if ($sshErr) { $sshErr } else { '(nothing)' }). $why"
}
if ($Heads -notcontains $vmHead) { Stop-Step WHERE "prod's code is $short, this window expects $(($Heads | ForEach-Object { $_.Substring(0,7) }) -join ' or ')" }

$names = ($Kits | ForEach-Object { $_.Split(':')[0] }) -join ' '
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$remote = "/tmp/rt6-window-back-$ts.tar"
& ssh -o BatchMode=yes $Vm "cd /tmp && ls -d $(($names.Split(' ') | ForEach-Object { "$_/out-*" }) -join ' ') 2>/dev/null | xargs -r tar -cf $remote && ls -l $remote"
if ($LASTEXITCODE -ne 0) { Stop-Step FETCH "could not pack the out-* folders on prod (exit $LASTEXITCODE)" }
$dest = Join-Path $Back "rt6-window-back-$ts.tar"
& scp -q -o BatchMode=yes "${Vm}:$remote" $dest
if ($LASTEXITCODE -ne 0) { Stop-Step FETCH "scp back failed (exit $LASTEXITCODE)" }
& ssh -o BatchMode=yes $Vm "rm -f $remote"
$bsha = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLower()
Write-Host ""
Write-Host "######## DONE - tell the CA: $dest (sha256 $($bsha.Substring(0,12))...)"
