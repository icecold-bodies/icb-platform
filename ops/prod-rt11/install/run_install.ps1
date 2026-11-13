# RT11 - WeasyPrint for the letterhead quote on prod: ONE line per step of the release window, from PowerShell or
# Command Prompt (the release runbook gives each one as its own numbered block):
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt11-stage\install\run_install.ps1" preflight
#
# Steps: preflight (read only) . apt . pip . verify (read only) . rollback. RT11's tested check line
# (ops/prod-rt11/run_check.ps1), its names changed and the step added:
# 1. copies rt11_install_vm.sh (beside this file) to prod as /tmp/icb-rt11-install-vm.sh and runs it BY PATH to read
#    prod's machine, HEAD and boot time: the FIRST line names them and the step, and a wrong place is refused first;
# 2. copies the kit (icb-rt11-install.tar), unpacks, verifies and stamps it there;
# 3. runs the step BY PATH under sudo over ssh -t - one of five FIXED remote lines below, chosen by the step's name
#    (sudo asks for the VM password; nothing shows while you type); the step removes its own kit when it ends;
# 4. fetches the report to Downloads\rt11-install-<step>-<date-time>.txt;
# 5. reads back that prod /tmp holds nothing of the kit (the helper removes the report, then itself).
# No script text is ever handed to ssh as an argument (RT8, 21 Oct). ASCII only: Windows PowerShell 5.1 reads a
# BOM-less file as ANSI. Filled in by mkstage_install.sh: __STAGED_FROM__ __EXPECT_HEADS__ __VM_SHA__ __KIT_SHA__.
param([string]$Step = '')
$ErrorActionPreference = 'Continue'   # native ssh / scp write to stderr; every exit code is checked by hand
$Here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Staged = '__STAGED_FROM__'
$Heads  = '__EXPECT_HEADS__'.Split(' ')
$VmSha  = '__VM_SHA__'
$KitSha = '__KIT_SHA__'
$Vm     = 'mickeyger@192.168.0.251'
$VmName = 'icb-mes-prod'
$PcName = 'LAPTOP-DGJ0U6RQ'
$VmFile = Join-Path $Here 'rt11_install_vm.sh'
$Tar    = Join-Path $Here 'icb-rt11-install.tar'
$Steps  = @{
  'preflight' = 'sudo bash /tmp/icb-rt11-install/rt11_install.sh preflight'
  'apt'       = 'sudo bash /tmp/icb-rt11-install/rt11_install.sh apt'
  'pip'       = 'sudo bash /tmp/icb-rt11-install/rt11_install.sh pip'
  'verify'    = 'sudo bash /tmp/icb-rt11-install/rt11_install.sh verify'
  'rollback'  = 'sudo bash /tmp/icb-rt11-install/rt11_install.sh rollback'
}
$ReadOnly = @('preflight', 'verify')

function Stop-Step($tag, $why, $after) {
  Write-Host ""
  Write-Host "######## STOP [$tag]: $why"
  if ($after) { Write-Host "######## $after" } else { Write-Host "######## nothing was changed on prod. Copy the whole window and paste it back to the CA." }
  exit 1
}

# ---- 1. where am I? (the first line, before anything else) ---------------------------------------------------------
$vmHost = '?'; $vmHead = '?'; $vmBoot = '?'; $why = ''
$sha = if (Test-Path $VmFile) { (Get-FileHash -Algorithm SHA256 $VmFile).Hash.ToLower() } else { 'missing' }
$tarSha = if (Test-Path $Tar) { (Get-FileHash -Algorithm SHA256 $Tar).Hash.ToLower() } else { 'missing' }
$errFile = [System.IO.Path]::GetTempFileName()
if (-not $Steps.ContainsKey($Step)) {
  $why = "STEP|'$Step' is not a step: preflight, apt, pip, verify or rollback"
} elseif ($sha -ne $VmSha) {
  $why = "KIT|$VmFile is $sha, the stage wrote $VmSha - tell the CA"
} elseif ($tarSha -ne $KitSha) {
  $why = "KIT|$Tar is $tarSha, the stage wrote $KitSha - tell the CA"
} else {
  # no -q: scp -q also silences ssh's own reason (RT9, 22 Oct); its progress line goes to $null instead
  & scp -o BatchMode=yes -o ConnectTimeout=10 $VmFile "${Vm}:/tmp/icb-rt11-install-vm.sh" > $null 2>$errFile
  if ($LASTEXITCODE -ne 0) {
    $why = "WHERE|could not copy the helper to prod (scp exit $LASTEXITCODE)"
  } else {
    $probe = & ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm 'bash /tmp/icb-rt11-install-vm.sh where' 2>$errFile
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
Write-Host "######## RT11 install: $Step . machine $env:COMPUTERNAME -> $vmHost . head $short . boot $vmBoot . stage $($Staged.Substring(0,7)) . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
if ($why) { $t, $w = $why.Split('|', 2); if ($t -eq 'WHERE') { $w = "$w. It said: $said. $hint" }; Stop-Step $t $w }
if ($env:COMPUTERNAME -ne $PcName) { Stop-Step WHERE "this is $env:COMPUTERNAME; the stage lives on $PcName" }
if ($vmHost -ne $VmName) { Stop-Step WHERE "ssh $Vm reached '$vmHost', not $VmName. ssh said: $said. $hint" }
if ($vmBoot -notmatch '^\d{4}-\d{2}-\d{2} ') { Stop-Step WHERE "prod's boot time could not be read ('$vmBoot') - tell the CA" }
if ($Heads -notcontains $vmHead) { Stop-Step WHERE "prod's code is $short, this kit expects $(($Heads | ForEach-Object { $_.Substring(0,7) }) -join ' or ')" }

# ---- 2. the kit -----------------------------------------------------------------------------------------------------
Write-Host "== kit ok: icb-rt11-install.tar sha256 $($tarSha.Substring(0,12))..."
& scp -o BatchMode=yes -o ConnectTimeout=10 $Tar "${Vm}:/tmp/icb-rt11-install.tar" > $null
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "scp of the kit failed (exit $LASTEXITCODE)" "nothing ran on prod. Paste the same line again." }
& ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm 'bash /tmp/icb-rt11-install-vm.sh unpack'
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "the kit did not unpack cleanly on prod (exit $LASTEXITCODE)" "nothing ran on prod. Paste the same line again." }

# ---- 3. the step, under sudo ----------------------------------------------------------------------------------------
$remote = $Steps[$Step]
Write-Host "== on prod: $remote"
Write-Host "== sudo asks for the VM password next; nothing shows while you type. Then wait for the ######## line."
& ssh -t -o BatchMode=yes -o ConnectTimeout=10 $Vm $remote
$rc = $LASTEXITCODE

# ---- 4. the report, to Downloads ------------------------------------------------------------------------------------
$dl = Join-Path $env:USERPROFILE 'Downloads'
$local = Join-Path $dl ("rt11-install-$Step-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".txt")
& scp -o BatchMode=yes -o ConnectTimeout=10 "${Vm}:/tmp/icb-rt11-install-report.txt" $local > $null
$fetched = ($LASTEXITCODE -eq 0) -and (Test-Path $local)
if ($fetched) { Write-Host "== the report: $local ($((Get-Item $local).Length) bytes)" } else { Write-Host "== the report could not be fetched (scp exit $LASTEXITCODE); the window above holds it" }

# ---- 5. prod /tmp read back ------------------------------------------------------------------------------------------
Write-Host "== prod /tmp read back (the helper removes the report, then itself):"
& ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm 'bash /tmp/icb-rt11-install-vm.sh readback'
$rb = $LASTEXITCODE
Write-Host ""
$what = if ($ReadOnly -contains $Step) { 'read only' } else { 'it changes prod' }
if ($rb -ne 0) { Stop-Step READBACK "prod /tmp still holds part of the kit (exit $rb) - read the lines above" "the step itself ended with exit $rc. Copy the whole window and paste it back to the CA." }
if ($rc -ne 0) { Stop-Step $Step.ToUpper() "the $Step step ended with exit $rc - read its STOP line above: it says what was and was not changed" "Prod /tmp is clean. Copy the whole window and paste it back to the CA." }
if (-not $fetched) { Stop-Step FETCH "the $Step step ran (exit 0) but its report did not reach Downloads" "the window above holds the whole report. Prod /tmp is clean. Copy the whole window and paste it back to the CA." }
Write-Host "######## DONE - $Step ($what). Report: $local. Prod /tmp is clean. Copy the whole window and paste it back to the CA."
exit 0
