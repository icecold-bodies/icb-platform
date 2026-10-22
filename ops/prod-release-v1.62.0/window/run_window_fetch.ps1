# RT9 window, step 9 - bring this window's run records (every kit's out-* folder written since the copy line) back
# from prod /tmp to Downloads, in ONE tar. ONE line, from PowerShell OR Command Prompt:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_fetch.ps1"
#
# Read only on prod, except the one tar it writes in /tmp and removes again once it is on this laptop. No sudo, so no
# password (the out-* folders are world-readable). Nothing under /var/backups is read.
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'window_common.ps1')
$Back = Join-Path $env:USERPROFILE 'Downloads'

Enter-Window 'fetch (step 9)'
$name = "rt9-window-back-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
& ssh -o BatchMode=yes $Vm "bash /tmp/icb-rt9-vm.sh fetch $name"
if ($LASTEXITCODE -ne 0) { Stop-Step FETCH "could not pack the out-* folders on prod (exit $LASTEXITCODE)" }
$dest = Join-Path $Back "$name.tar"
& scp -q -o BatchMode=yes "${Vm}:/tmp/$name.tar" $dest
if ($LASTEXITCODE -ne 0) { Stop-Step FETCH "scp back failed (exit $LASTEXITCODE)" "/tmp/$name.tar stays on prod for now. Copy the whole window and paste it back to the CA." }
& ssh -o BatchMode=yes $Vm "bash /tmp/icb-rt9-vm.sh rmfetch $name"
$bsha = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLower()
$size = (Get-Item $dest).Length
Write-Host ""
Write-Host "######## DONE - step 9: $dest ($size bytes, sha256 $($bsha.Substring(0,12))...). Copy the whole window and paste it back to the CA."
