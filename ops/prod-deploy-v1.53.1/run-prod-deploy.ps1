<#
.SYNOPSIS
  v1.53.1 prod deploy launcher: copies the deploy kit to the prod VM, runs ONE action
  over YOUR ssh session, and fetches that run's log back to .\out\<stamp>\.

.DESCRIPTION
  Actions (each is a separate, deliberate run):
    VerifyBaseline  read-only - proves today's prod is exactly 04b332f (run BEFORE Deploy; expect green)
    Verify       read-only - proves prod is exactly 94ed70b (run AFTER Deploy; expect green)
    Deploy       04b332f -> 94ed70b; shows the plan, then asks you to type DEPLOY
    Rollback     94ed70b -> 04b332f; asks you to type ROLLBACK
    SeedDryRun   read-only preview of the #184 Manni RIGIDS CB default thicknesses
    SeedApply    backup + snapshot + write + verify; asks you to type SEED
    SeedRestore  put the Manni draft back from a snapshot (-RestoreFile); asks RESTORE

  You type the SSH password at each ssh/scp prompt (3 prompts: copy, run, fetch) and your
  sudo password on the VM if your account needs one. Nothing here stores a password.
  Pure ASCII on purpose: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\run-prod-deploy.ps1 -Action VerifyBaseline
  powershell -ExecutionPolicy Bypass -File .\run-prod-deploy.ps1 -Action Deploy
  powershell -ExecutionPolicy Bypass -File .\run-prod-deploy.ps1 -Action Verify
  powershell -ExecutionPolicy Bypass -File .\run-prod-deploy.ps1 -Action Deploy -DryRun
#>
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("VerifyBaseline", "Verify", "Deploy", "Rollback", "SeedDryRun", "SeedApply", "SeedRestore")]
  [string]$Action,
  [string]$User = "icb",
  [string]$VmHost = "192.168.0.251",
  [string]$RemoteDir = "icb-deploy-v1531",     # relative to the remote home directory
  [string]$RestoreFile = "",                   # SeedRestore only: path ON THE VM to a manni_draft_before_*.json
  [switch]$Restart,                            # Deploy only: also restart icb-backend (not needed for this release)
  [switch]$DryRun                              # stage + print the commands, contact nothing
)

$ErrorActionPreference = "Stop"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$kitSrc = Join-Path $here "kit"
$target = "$User@$VmHost"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"

foreach ($exe in @("ssh", "scp")) {
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { throw "$exe not found - install the Windows OpenSSH client." }
}
if ($Action -eq "SeedRestore" -and -not $RestoreFile) { throw "SeedRestore needs -RestoreFile <path on the VM>, e.g. ~/$RemoteDir/manni_draft_before_<run>.json" }
if ($RestoreFile -match "[^A-Za-z0-9_./~-]") { throw "-RestoreFile may only contain letters, digits and _ . / ~ -" }
if ($Restart -and $Action -ne "Deploy") { throw "-Restart only applies to -Action Deploy" }

switch ($Action) {
  "VerifyBaseline" { $remoteCmd = "bash ~/$RemoteDir/verify.sh $stamp baseline" }
  "Verify"      { $remoteCmd = "bash ~/$RemoteDir/verify.sh $stamp target" }
  "Deploy"      { $remoteCmd = "bash ~/$RemoteDir/deploy.sh $stamp" + $(if ($Restart) { " --restart" } else { "" }) }
  "Rollback"    { $remoteCmd = "bash ~/$RemoteDir/rollback.sh $stamp" }
  "SeedDryRun"  { $remoteCmd = "bash ~/$RemoteDir/seed_manni_defaults.sh $stamp dry-run" }
  "SeedApply"   { $remoteCmd = "bash ~/$RemoteDir/seed_manni_defaults.sh $stamp apply" }
  "SeedRestore" { $remoteCmd = "bash ~/$RemoteDir/seed_manni_defaults.sh $stamp restore $RestoreFile" }
}

# Stage an LF-only copy: a CRLF bash script dies on the VM with "$'\r': command not found".
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "icb-deploy-stage-$stamp"
$stageKit = Join-Path $stage $RemoteDir
New-Item -ItemType Directory -Force -Path $stageKit | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
Get-ChildItem -Path $kitSrc -File | ForEach-Object {
  $text = [System.IO.File]::ReadAllText($_.FullName) -replace "`r`n", "`n"
  [System.IO.File]::WriteAllText((Join-Path $stageKit $_.Name), $text, $utf8)
}
Write-Host ("Action: {0}   Staged (LF): {1}" -f $Action, ((Get-ChildItem -Path $stageKit -File | ForEach-Object { $_.Name }) -join ", "))

$localOut = Join-Path $here "out\$stamp-$Action"
if ($DryRun) {
  Write-Host "[dry-run] scp -r `"$stageKit`" `"${target}:`""
  Write-Host "[dry-run] ssh -t $target `"$remoteCmd`""
  Write-Host "[dry-run] scp -r `"${target}:$RemoteDir/out-latest/*`" `"$localOut`""
  Write-Host "[dry-run] stage left at $stage for inspection"
  exit 0
}

Write-Host ""
Write-Host "[1/3] Copying the deploy kit to ${target}:~/$RemoteDir  (enter the SSH password if asked)" -ForegroundColor Cyan
& scp -r "$stageKit" "${target}:"
if ($LASTEXITCODE -ne 0) { throw "scp upload failed (exit $LASTEXITCODE) - nothing was run on the VM." }

Write-Host ""
Write-Host "[2/3] Running '$Action' on the VM  (SSH password, then sudo password if asked; type the confirmation word when shown)" -ForegroundColor Cyan
& ssh -t "$target" "$remoteCmd"
$runExit = $LASTEXITCODE
Write-Host "remote exit code: $runExit"
if ($runExit -eq 255) {
  Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
  throw "ssh failed (exit 255: login/connection). Nothing fetched. If this was Deploy, run -Action Verify to see where prod is before retrying."
}

New-Item -ItemType Directory -Force -Path $localOut | Out-Null
Write-Host ""
Write-Host "[3/3] Fetching the run log to $localOut  (enter the SSH password if asked)" -ForegroundColor Cyan
& scp -r "${target}:$RemoteDir/out-latest/*" "$localOut"
$fetchExit = $LASTEXITCODE
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue

$runIdFile = Join-Path $localOut "RUN_ID"
$fresh = (Test-Path $runIdFile) -and (((Get-Content $runIdFile -Raw) -replace "\s", "") -eq $stamp)
Write-Host ""
if ($fetchExit -ne 0) {
  Write-Warning "scp fetch failed (exit $fetchExit) - the log is on the VM under ~/$RemoteDir/out-latest"
} elseif (-not $fresh) {
  Write-Warning "The fetched log is NOT from this run (RUN_ID does not match $stamp). Ignore it and read the terminal output above."
} elseif ($runExit -ne 0) {
  Write-Warning "'$Action' did NOT complete (exit $runExit). Log: $localOut. Read the STOP line above before doing anything else."
} else {
  Write-Host "'$Action' completed. Log: $localOut" -ForegroundColor Green
  Write-Host "Tell Claude '$Action done' - it reads that folder directly."
}
exit $runExit
