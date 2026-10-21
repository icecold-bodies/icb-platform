# RT9 window - shared by run_window_copy.ps1, run_window_step.ps1, run_window_fetch.ps1 and run_window_cleanup.ps1
# (dot-sourced; never run on its own). ASCII only: Windows PowerShell 5.1 reads a BOM-less file as ANSI.
#
# Every line first copies rt9_vm.sh (beside this file) to prod as /tmp/icb-rt9-vm.sh and runs it BY PATH to read
# prod's machine name, HEAD and boot time; the FIRST line it prints names this laptop, prod's machine, prod's HEAD
# and boot time, and it refuses a wrong place before anything runs. No script text is ever handed to ssh as an
# argument (RT8, 21 Oct: Windows PowerShell 5.1 dropped the double quotes inside one, and bash ran nothing).
# Filled in by mkstage_window.sh: __STAGED_FROM__ __EXPECT_HEADS__ __VM_SHA__.
$ErrorActionPreference = 'Continue'   # native ssh / scp write to stderr; every exit code is checked by hand
$Staged = '__STAGED_FROM__'
$Heads  = '__EXPECT_HEADS__'.Split(' ')
$VmSha  = '__VM_SHA__'
$Vm     = 'mickeyger@192.168.0.251'
$VmName = 'icb-mes-prod'
$PcName = 'LAPTOP-DGJ0U6RQ'
$VmFile = Join-Path $Here 'rt9_vm.sh'

function Stop-Step($tag, $why, $after) {
  Write-Host ""
  Write-Host "######## STOP [$tag]: $why"
  if ($after) { Write-Host "######## $after" } else { Write-Host "######## nothing was changed on prod. Copy the whole window and paste it back to the CA." }
  exit 1
}

# copy the helper, read prod's identity, print the first line, refuse a wrong place. Returns nothing; sets $script:VmHead.
function Enter-Window($label) {
  $vmHost = '?'; $vmHead = '?'; $vmBoot = '?'; $why = ''
  $sha = if (Test-Path $VmFile) { (Get-FileHash -Algorithm SHA256 $VmFile).Hash.ToLower() } else { 'missing' }
  $errFile = [System.IO.Path]::GetTempFileName()
  if ($sha -ne $VmSha) {
    $why = "KIT|$VmFile is $sha, the stage wrote $VmSha - re-stage"
  } else {
    & scp -q -o BatchMode=yes -o ConnectTimeout=10 $VmFile "${Vm}:/tmp/icb-rt9-vm.sh" 2>$errFile
    if ($LASTEXITCODE -ne 0) {
      $why = "WHERE|could not copy the helper to prod (scp exit $LASTEXITCODE)"
    } else {
      $probe = & ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm 'bash /tmp/icb-rt9-vm.sh where' 2>$errFile
      if ($probe) { $vmHost = "$($probe[0])".Trim() }
      if ($probe -and $probe.Count -gt 1) { $vmHead = "$($probe[1])".Trim() }
      if ($probe -and $probe.Count -gt 2) { $vmBoot = "$($probe[2])".Trim() }
    }
  }
  $sshErr = ((Get-Content $errFile -ErrorAction SilentlyContinue) -join ' ').Trim()
  Remove-Item $errFile -ErrorAction SilentlyContinue
  $said = if ($sshErr) { $sshErr } else { '(nothing)' }
  $hint = if ($sshErr -match 'timed out|No route|unreachable|Could not resolve') { 'prod is not reachable on the LAN address - connect the VPN, then paste the same line again' } else { 'tell the CA' }
  $short = if ($vmHead.Length -ge 7) { $vmHead.Substring(0, 7) } else { $vmHead }
  Write-Host "######## RT9 window $label . machine $env:COMPUTERNAME -> $vmHost . head $short . boot $vmBoot . stage $($Staged.Substring(0,7)) . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
  if ($why) { $t, $w = $why.Split('|', 2); if ($t -eq 'WHERE') { $w = "$w. It said: $said. $hint" }; Stop-Step $t $w }
  if ($env:COMPUTERNAME -ne $PcName) { Stop-Step WHERE "this is $env:COMPUTERNAME; the stage lives on $PcName" }
  if ($vmHost -ne $VmName) { Stop-Step WHERE "ssh $Vm reached '$vmHost', not $VmName. ssh said: $said. $hint" }
  if ($vmBoot -notmatch '^\d{4}-\d{2}-\d{2} ') { Stop-Step WHERE "prod's boot time could not be read ('$vmBoot') - tell the CA" }
  if ($Heads -notcontains $vmHead) { Stop-Step WHERE "prod's code is $short, this window expects $(($Heads | ForEach-Object { $_.Substring(0,7) }) -join ' or ')" }
  $script:VmHead = $vmHead
}
