# RT12 - after the :8000 restart (post-merge block B): is :8000 serving what Michael's clone now holds? READ ONLY.
# ONE line, PowerShell:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\local\check_8000.ps1"
#
# 1. /static/js/calculator.js?v=192 and /static/js/calculator2.js?v=129 (the ?v= each template on disk loads): the
#    bytes :8000 serves = the bytes on disk in the clone (sha256);
# 2. /mes-app/assets/<bundle>: the SPA bundle the clone's frontend\dist\index.html names, served = the clone's file,
#    and it carries RT10's text ("is the latest. Accept REV");
# 3. /health/version: the running python's version line must read v1.63.0 (last, so 1 and 2 are reported either way).
# -Base / -Clone / -Version exist for the CA's own test run only; Michael runs it with none. ASCII only (PS 5.1 reads ANSI).
param([string]$Base = 'http://127.0.0.1:8000', [string]$Clone = 'C:\Users\micge\Documents\icb-platform', [string]$Version = 'v1.63.0')
$ErrorActionPreference = 'Continue'
$bad = @()
Write-Host "######## RT12 :8000 check (read only) . $Base . clone $Clone . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
  $h = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "$Base/health/version").Content
  Write-Host "   health      $h"
} catch {
  Write-Host ""
  Write-Host "######## STOP [DOWN]: $Base does not answer - is the start.bat window running and showing 'Application startup complete.'?"
  exit 1
}
function Served-Sha($url) {
  $tmp = [System.IO.Path]::GetTempFileName()
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 $url -OutFile $tmp; $s = (Get-FileHash -Algorithm SHA256 $tmp).Hash.ToLower() } catch { $s = 'none' }
  Remove-Item $tmp -ErrorAction SilentlyContinue
  return $s
}
function Short($s) { if ($s.Length -ge 12) { $s.Substring(0, 12) } else { $s } }
foreach ($pair in @(@('calculator.html', 'calculator.js'), @('calculator2.html', 'calculator2.js'))) {
  $tplName, $jsName = $pair
  $js = Join-Path $Clone "backend\app\static\js\$jsName"
  $tpl = Join-Path $Clone "backend\app\templates\$tplName"
  $v = ([regex]::Match([System.IO.File]::ReadAllText($tpl), [regex]::Escape($jsName) + '\?v=(\d+)')).Groups[1].Value
  $served = Served-Sha "$Base/static/js/$jsName`?v=$v"
  $disk = (Get-FileHash -Algorithm SHA256 $js).Hash.ToLower()
  $ok = if ($served -eq $disk) { 'yes' } else { $bad += $jsName; 'NO' }
  Write-Host "   $($jsName.PadRight(15)) ?v=$v served $(Short $served) disk $(Short $disk) same: $ok"
}
# the SPA page itself needs a session (it redirects to /login), so the check fetches the bundle the clone's
# index.html names and compares its bytes with the clone's file
$distIndex = [System.IO.File]::ReadAllText((Join-Path $Clone 'frontend\dist\index.html'))
$want = ([regex]::Match($distIndex, 'index-[A-Za-z0-9_-]+\.js')).Value
$got = Served-Sha "$Base/mes-app/assets/$want"
$bundle = Join-Path $Clone "frontend\dist\assets\$want"
$have = (Get-FileHash -Algorithm SHA256 $bundle).Hash.ToLower()
$ok2 = if ($got -eq $have) { 'yes' } else { $bad += 'SPA'; 'NO' }
Write-Host "   SPA bundle      $want served $(Short $got) clone $(Short $have) same: $ok2"
$mark = ([System.IO.File]::ReadAllText($bundle)).Contains('is the latest. Accept REV')
$ok3 = if ($mark) { 'yes' } else { $bad += 'SPA text'; 'NO' }
Write-Host "   SPA text        RT10's 'is the latest. Accept REV' in the clone's bundle: $ok3"
Write-Host ""
if ($bad.Count -gt 0) {
  Write-Host "######## STOP [OLD]: $($bad -join ' and ') served by :8000 is not the clone's - close the start.bat window, start it again, then paste this line again"
  exit 1
}
if ($h -notmatch ('"version":"' + [regex]::Escape($Version) + '"')) {
  Write-Host "######## STOP [VERSION]: :8000 says $h, not $Version - the python that runs started before the clone moved: close the start.bat window, start it again, then paste this line again"
  exit 1
}
Write-Host "######## DONE - :8000 serves $Version (calculator.js and calculator2.js = the clone, SPA $want = the clone, with RT10's text). Copy the whole window and paste it back to the CA."
exit 0
