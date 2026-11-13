# RT11 - WeasyPrint in Michael's :8000 venv, AFTER the merge and the fast-forward of his clone. ONE line, PowerShell:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-platform\ops\prod-rt11\laptop\install_venv.ps1"
#
# 1. refuses unless the clone carries RT11 (requirements.txt pins weasyprint==70.0; the shipped faces are there) and the
#    GTK3 runtime is installed (WeasyPrint's Pango on Windows; present on this laptop since 26 Apr 2026);
# 2. installs exactly the lock (ops/prod-rt11/install/weasyprint-lock.txt, the 10 packages prod gets) with --no-deps;
# 3. reads back: the venv gained exactly the lock, nothing else changed, weasyprint imports 70.0, and the gate
#    (report_engine.check_letterhead_quote) reads True with the clone's code;
# 4. says to restart :8000 (start.bat): the server reads the gate at start-up, then the results page offers
#    "Generate Quote" instead of "Official quotes are issued from SAP.".
# Run again: "already installed". ASCII only (Windows PowerShell 5.1). -Repo exists for the sim only.
param([string]$Repo = 'C:\Users\micge\Documents\icb-platform')
$ErrorActionPreference = 'Continue'
$Backend = Join-Path $Repo 'backend'
$Py      = Join-Path $Backend '.venv\Scripts\python.exe'
$Lock    = (Resolve-Path (Join-Path $PSScriptRoot '..\install\weasyprint-lock.txt')).Path
$Gtk     = 'C:\Program Files\GTK3-Runtime Win64\bin\libpango-1.0-0.dll'
function Stop-Step($tag, $why) { Write-Host ""; Write-Host "######## STOP [$tag]: $why"; Write-Host "######## nothing was installed. Copy the whole window and paste it back to the CA."; exit 1 }
function Freeze() { @(& $Py -m pip list --format=freeze --disable-pip-version-check 2>$null | ForEach-Object { "$_".ToLower().Replace('_', '-') } | Sort-Object) }

Write-Host "######## RT11 laptop venv . $Py . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
if (-not (Test-Path $Py)) { Stop-Step VENV "no venv python at $Py" }
$req = Get-Content (Join-Path $Backend 'requirements.txt') -ErrorAction SilentlyContinue
if (-not ($req -contains 'weasyprint==70.0')) { Stop-Step CODE "the clone's requirements.txt does not pin weasyprint==70.0: fast-forward the clone to the RT11 merge first" }
if (-not (Test-Path (Join-Path $Backend 'app\static\fonts\LiberationSans-Regular.ttf'))) { Stop-Step CODE "the clone has no shipped faces (app\static\fonts): fast-forward it first" }
if (-not (Test-Path $Gtk)) { Stop-Step GTK "the GTK3 runtime is not installed ($Gtk): without it WeasyPrint cannot load and :8000 keeps the SAP line" }
Write-Host "== the clone carries RT11; the GTK3 runtime is installed"

$want = @(Get-Content $Lock | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim().ToLower() } | Sort-Object)
$before = Freeze
$missing = @($want | Where-Object { $before -notcontains $_ })
if ($missing.Count -eq 0) {
  Write-Host "== every package of the lock is already installed at its version: nothing to do"
} else {
  Write-Host "== pip install --no-deps -r $Lock"
  & $Py -m pip install --disable-pip-version-check --no-deps -r $Lock 2>&1 | Where-Object { "$_" -match '^(Successfully installed|ERROR)' } | ForEach-Object { Write-Host "   $_" }
  if ($LASTEXITCODE -ne 0) { Stop-Step PIP "pip install ended with exit $LASTEXITCODE" }
  $after = Freeze
  $gained = @($after | Where-Object { $before -notcontains $_ })
  $lost = @($before | Where-Object { $after -notcontains $_ })
  Write-Host "   the venv gained: $($gained -join ' ')"
  if ($lost.Count -ne 0) { Write-Host ""; Write-Host "######## STOP [PIP]: an installed package changed: $($lost -join ' ')"; Write-Host "######## tell the CA (it lists what to uninstall)."; exit 1 }
  if ((($gained | Sort-Object) -join ' ') -ne ($missing -join ' ')) { Write-Host ""; Write-Host "######## STOP [PIP]: the venv gained more or less than the lock"; Write-Host "######## tell the CA."; exit 1 }
}
$ver = & $Py -I -c "import weasyprint; print(weasyprint.__version__)" 2>$null | Select-Object -Last 1
if ("$ver".Trim() -ne '70.0') { Write-Host ""; Write-Host "######## STOP [IMPORT]: weasyprint imports as '$ver', not 70.0"; Write-Host "######## tell the CA."; exit 1 }
$gate = & $Py -I -c "import sys; sys.path.insert(0, r'$Backend'); from app import report_engine as r; print(r.check_letterhead_quote())" 2>$null | Select-Object -Last 1
Write-Host "== weasyprint imports $ver; the gate with the clone's code reads $gate"
if ("$gate".Trim() -ne 'True') { Write-Host ""; Write-Host "######## STOP [GATE]: the gate reads '$gate'"; Write-Host "######## WeasyPrint is installed; :8000 keeps the SAP line. Tell the CA."; exit 1 }
Write-Host ""
Write-Host "######## DONE - WeasyPrint 70.0 in the :8000 venv; the gate reads True. Restart :8000 (start.bat), then copy the whole window and paste it back to the CA."
exit 0
