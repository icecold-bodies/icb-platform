# RT9 window - run ONE step of the window on prod from this laptop: ssh to the VM and run the staged kit there BY
# PATH, under sudo (it asks for the VM password; nothing shows while you type). ONE line per step, from PowerShell OR
# Command Prompt; the word at the end names the step:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_step.ps1" preflight
#
#   preflight    step 2  sudo bash /tmp/icb-release-v1.62.0/release.sh preflight   (read only)
#   all-before   step 3  sudo bash /tmp/icb-rt2-all/rt2_all.sh pre                 (read only; after the page's All)
#   deploy       step 4  sudo bash /tmp/icb-release-v1.62.0/release.sh deploy
#   all-after    step 5  sudo bash /tmp/icb-rt2-all/rt2_all.sh post                (read only; after the page's All)
#   doors        step 6  sudo bash /tmp/icb-rt2-doors/rt2_doors.sh                 (read only)
#   verify       step 8  sudo bash /tmp/icb-release-v1.62.0/release.sh verify      (read only; after the N10022 check)
#
# The output is NOT piped: sudo needs the terminal to ask for the password (a pipe hangs it with no prompt).
param([Parameter(Position = 0)][string]$Step = '')
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'window_common.ps1')
$Plan = @{
  'preflight'  = @('2', 'preflight (read only)',  'sudo bash /tmp/icb-release-v1.62.0/release.sh preflight', $true)
  'all-before' = @('3', 'All before (read only)', 'sudo bash /tmp/icb-rt2-all/rt2_all.sh pre', $true)
  'deploy'     = @('4', 'deploy',                 'sudo bash /tmp/icb-release-v1.62.0/release.sh deploy', $false)
  'all-after'  = @('5', 'All after (read only)',  'sudo bash /tmp/icb-rt2-all/rt2_all.sh post', $true)
  'doors'      = @('6', 'doors (read only)',      'sudo bash /tmp/icb-rt2-doors/rt2_doors.sh', $true)
  'verify'     = @('8', 'verify (read only)',     'sudo bash /tmp/icb-release-v1.62.0/release.sh verify', $true)
}
if (-not $Plan.ContainsKey($Step)) {
  Write-Host "######## STOP [STEP]: the line must end with one of: preflight all-before deploy all-after doors verify (it ended with '$Step')"
  Write-Host "######## nothing was run. Copy the line from the CA's message again."
  exit 1
}
$n, $what, $remote, $readOnly = $Plan[$Step]

Enter-Window "step $n $what"
Write-Host "== on prod: $remote"
Write-Host "== sudo asks for the VM password next; nothing shows while you type. Then wait for the ######## line."
& ssh -t -o BatchMode=yes -o ConnectTimeout=10 $Vm $remote
$rc = $LASTEXITCODE
Write-Host ""
if ($rc -eq 0) {
  Write-Host "######## DONE - step $n ($Step) ended with exit 0. Copy the whole window and paste it back to the CA."
  exit 0
}
if ($readOnly) {
  Stop-Step "STEP $n" "$Step ended with exit $rc - read the STOP line above" "this step is read only: nothing was changed. Run nothing else; copy the whole window and paste it back to the CA."
}
Stop-Step "STEP $n" "$Step ended with exit $rc - read the STOP line above" "run NOTHING else (not even this line again) until the CA answers. Copy the whole window and paste it back to the CA."
