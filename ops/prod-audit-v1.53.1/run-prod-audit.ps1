<#
.SYNOPSIS
  v1.53.1 prod audit launcher (READ-ONLY): copies the audit kit to the prod VM,
  runs it over YOUR ssh session, and fetches the results back to .\out\<stamp>\.

.DESCRIPTION
  You type the SSH password at each ssh/scp prompt (3 prompts: copy, run, fetch),
  plus your sudo password on the VM if your account needs one. Nothing here stores
  or forwards a password. The kit only reads prod: git/curl probes and a Python
  audit whose database session is forced read-only and rolled back.

  This file is kept pure ASCII on purpose: Windows PowerShell 5.1 reads a BOM-less
  script as ANSI, and a single non-ASCII dash breaks parsing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\run-prod-audit.ps1
  powershell -ExecutionPolicy Bypass -File .\run-prod-audit.ps1 -User michael
  powershell -ExecutionPolicy Bypass -File .\run-prod-audit.ps1 -DryRun
#>
param(
  [string]$User = "icb",
  [string]$VmHost = "192.168.0.251",
  [string]$RemoteDir = "icb-prod-audit-v1531",   # relative to the remote home directory
  [switch]$DryRun                                 # stage + print the commands, run nothing remote
)

$ErrorActionPreference = "Stop"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$kitSrc = Join-Path $here "kit"
$target = "$User@$VmHost"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"

foreach ($exe in @("ssh", "scp")) {
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { throw "$exe not found - install the Windows OpenSSH client." }
}

# Stage an LF-only copy: a CRLF bash script dies on the VM with "$'\r': command not found".
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "icb-audit-stage-$stamp"
$stageKit = Join-Path $stage $RemoteDir
New-Item -ItemType Directory -Force -Path $stageKit | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
Get-ChildItem -Path $kitSrc -File | ForEach-Object {
  $text = [System.IO.File]::ReadAllText($_.FullName) -replace "`r`n", "`n"
  [System.IO.File]::WriteAllText((Join-Path $stageKit $_.Name), $text, $utf8)
}
$staged = (Get-ChildItem -Path $stageKit -File | ForEach-Object { $_.Name }) -join ", "
Write-Host "Staged (LF): $staged"

$localOut = Join-Path $here "out\$stamp"
if ($DryRun) {
  Write-Host "[dry-run] scp -r `"$stageKit`" `"${target}:`""
  Write-Host "[dry-run] ssh -t $target `"bash ~/$RemoteDir/audit.sh $stamp`""
  Write-Host "[dry-run] scp -r `"${target}:$RemoteDir/out-latest/*`" `"$localOut`""
  Write-Host "[dry-run] stage left at $stage for inspection"
  exit 0
}

Write-Host ""
Write-Host "[1/3] Copying the audit kit to ${target}:~/$RemoteDir  (enter the SSH password if asked)" -ForegroundColor Cyan
& scp -r "$stageKit" "${target}:"
if ($LASTEXITCODE -ne 0) { throw "scp upload failed (exit $LASTEXITCODE) - nothing was run on the VM." }

Write-Host ""
Write-Host "[2/3] Running the READ-ONLY audit on the VM  (SSH password, then sudo password if your account needs one)" -ForegroundColor Cyan
# The launch stamp is passed through so the VM stamps THIS run and the fetch below can prove freshness.
& ssh -t "$target" "bash ~/$RemoteDir/audit.sh $stamp"
$runExit = $LASTEXITCODE
Write-Host "audit exit code: $runExit"
if ($runExit -eq 255) {
  Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
  throw "ssh failed (exit 255: login/connection). Nothing fetched - rerun when ready."
}

New-Item -ItemType Directory -Force -Path $localOut | Out-Null
Write-Host ""
Write-Host "[3/3] Fetching results to $localOut  (enter the SSH password if asked)" -ForegroundColor Cyan
& scp -r "${target}:$RemoteDir/out-latest/*" "$localOut"
$fetchExit = $LASTEXITCODE
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue

$runIdFile = Join-Path $localOut "RUN_ID"
$fresh = (Test-Path $runIdFile) -and (((Get-Content $runIdFile -Raw) -replace "\s", "") -eq $stamp)
$hasSummary = Test-Path (Join-Path $localOut "SUMMARY.txt")
Write-Host ""
if ($fetchExit -ne 0) {
  Write-Warning "scp fetch failed (exit $fetchExit) - results (if any) are on the VM under ~/$RemoteDir/out-latest"
} elseif (-not $fresh) {
  Write-Warning "The fetched results are NOT from this run (RUN_ID does not match $stamp). Do not use them - check the audit output above."
} elseif ($runExit -ne 0 -or -not $hasSummary) {
  Write-Warning "Results fetched to $localOut, but the audit exited $runExit (summary present: $hasSummary) - NOT usable. See 00_code_state.txt / report.txt, fix, and rerun."
} else {
  Write-Host "Done. Fresh, complete results for run $stamp : $localOut" -ForegroundColor Green
  Write-Host "Tell Claude 'prod audit done' - it reads that folder directly (SUMMARY.txt, report.txt, CSVs)."
}
exit $runExit
