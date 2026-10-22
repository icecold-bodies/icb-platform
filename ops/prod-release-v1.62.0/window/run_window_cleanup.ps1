# RT9 close - remove the window's kits from prod /tmp BY EXACT NAME (the list is in rt9_vm.sh: NAMES), then read
# every name back from a second connection, then the helper removes itself. Run ONLY after the fetch (step 9) and on
# the CA's word. ONE line, from PowerShell OR Command Prompt:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_cleanup.ps1"
#
# The removal runs the copied file BY PATH under sudo (it asks for the VM password) - never an inline script (RT8's
# cleanup v1 ran nothing on 21 Oct: PowerShell 5.1 dropped the double quotes inside its ssh argument).
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'window_common.ps1')

Enter-Window 'close: prod /tmp cleanup'
Write-Host "== on prod: sudo bash /tmp/icb-rt9-vm.sh cleanup"
Write-Host "== sudo asks for the VM password next; nothing shows while you type."
& ssh -t -o BatchMode=yes -o ConnectTimeout=10 $Vm 'sudo bash /tmp/icb-rt9-vm.sh cleanup'
if ($LASTEXITCODE -ne 0) { Stop-Step CLEANUP "the cleanup ended with exit $LASTEXITCODE - read the lines above" "some names may be gone already. Copy the whole window and paste it back to the CA." }
Write-Host "== read back (a second connection, no sudo): every name must be absent"
& ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm 'bash /tmp/icb-rt9-vm.sh readback'
if ($LASTEXITCODE -ne 0) { Stop-Step READBACK "the read-back found a name still in /tmp (exit $LASTEXITCODE)" "copy the whole window and paste it back to the CA." }
Write-Host ""
Write-Host "######## DONE - prod /tmp: every RT9 window name removed and read back absent; the helper removed itself. Copy the whole window and paste it back to the CA."
