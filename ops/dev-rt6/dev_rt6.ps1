# RT6 - Michael's :8000 after the v1.61.0 merge (the post-merge procedure, before the window). ONE line per step,
# from PowerShell OR Command Prompt (ASCII only: Windows PowerShell 5.1 reads a BOM-less file as ANSI):
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-platform\ops\dev-rt6\dev_rt6.ps1" -Step upgrade -ExpectHead <merge-sha>
#   powershell ... -Step rules-dryrun -ExpectHead <merge-sha>
#   powershell ... -Step rules-apply  -ExpectHead <merge-sha>
#   powershell ... -Step rules-show   -ExpectHead <merge-sha>
#
# Stop :8000 before `upgrade` (start.bat would auto-upgrade on its own). The FIRST output line names this machine, the
# database (name @ host, from the LIVE session) and the main clone's HEAD; the step refuses unless they are
# LAPTOP-DGJ0U6RQ, icb @ localhost / 127.0.0.1:5432 and the merge commit (RT6 safe pastes). Only the URL's host and
# database name are ever printed - never a user or a password.
#   upgrade       a CHECKED full backup of icb (pg_dump -Fc; pg_restore -l must list the touched tables' data) into
#                 C:\Users\micge\Documents\icb_db_backups\, then `alembic upgrade 0053` (0052 -> 0053; 0053 = already);
#                 read back: alembic 0053 and the insulation_rule column
#   rules-*       ops/prod-rt6/rt6_rules.py --target dev (Burt's two rules; journaled; --show also lists dev's
#                 breaching costings by quote number). Apply journals into icb_db_backups\rt6-dev-rules\.
param(
  [Parameter(Mandatory = $true)][ValidateSet('upgrade', 'rules-dryrun', 'rules-apply', 'rules-show')][string]$Step,
  [Parameter(Mandatory = $true)][string]$ExpectHead
)
$ErrorActionPreference = 'Continue'
$Repo   = 'C:\Users\micge\Documents\icb-platform'
$Py     = "$Repo\backend\.venv\Scripts\python.exe"
$Keep   = 'C:\Users\micge\Documents\icb_db_backups'
$PcName = 'LAPTOP-DGJ0U6RQ'
function Stop-Step($tag, $why) { Write-Host ""; Write-Host "######## STOP [$tag]: $why"; Write-Host "######## nothing after this point ran. Tell the CA"; exit 1 }

# ---- where am I? (the first line) ----
$url = ''
$envFile = "$Repo\backend\.env"
if (Test-Path $envFile) {
  $line = Get-Content $envFile | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
  if ($line) { $url = ($line -replace '^\s*DATABASE_URL\s*=\s*', '').Trim().Trim('"').Trim("'") }
}
$pgUrl = $url -replace '^postgresql\+psycopg://', 'postgresql://'
$rest = $pgUrl -replace '^[a-z+]+://', ''
if ($rest -match '@') { $rest = $rest.Substring($rest.LastIndexOf('@') + 1) }
$dbHost = if ($rest) { $rest.Split('/')[0] } else { '?' }
$dbUrlName = if ($rest -match '/') { $rest.Substring($rest.IndexOf('/') + 1).Split('?')[0] } else { '?' }
$bin = (Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1)
$psql = if ($bin) { $bin.FullName } else { '' }
$db = '?'
if ($psql -and $pgUrl) {
  $env:PGOPTIONS = '-c default_transaction_read_only=on'
  $db = ("" + (& $psql -XAtc "select current_database()" $pgUrl 2>$null)).Trim(); if (-not $db) { $db = '?' }
  Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
}
$head = ("" + (& git -C $Repo rev-parse HEAD 2>$null)).Trim(); if (-not $head) { $head = '?' }
$h7 = if ($head.Length -ge 7) { $head.Substring(0, 7) } else { $head }
Write-Host "######## RT6 dev $Step . machine $env:COMPUTERNAME . db $db @ $dbHost . head $h7 . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$why = ''
if ($env:COMPUTERNAME -ne $PcName) { $why += " machine is '$env:COMPUTERNAME', this step runs on '$PcName';" }
if ($db -ne 'icb') { $why += " database is '$db', this step runs on 'icb';" }
if ($dbUrlName -ne 'icb') { $why += " the URL names database '$dbUrlName', not 'icb';" }
if (@('localhost:5432', '127.0.0.1:5432', 'localhost', '127.0.0.1') -notcontains $dbHost) { $why += " database host is '$dbHost', this step expects localhost:5432;" }
if ($head -ne $ExpectHead) { $why += " the main clone is at $h7, this step expects $($ExpectHead.Substring(0, [Math]::Min(7, $ExpectHead.Length)));" }
if ($why) { Stop-Step WHERE "WRONG PLACE -$why nothing was run" }
if (-not (Test-Path $Py)) { Stop-Step KIT "no python at $Py" }
$env:DATABASE_URL = $url
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'

function Get-Alembic { $env:PGOPTIONS = '-c default_transaction_read_only=on'; $a = ("" + (& $psql -XAtc "select string_agg(version_num, ',') from icb_costings.alembic_version" $pgUrl 2>&1)).Trim(); Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue; return $a }

if ($Step -eq 'upgrade') {
  $a = Get-Alembic
  Write-Host "== alembic before: $a"
  if ($a -eq '0053') { Write-Host "   already at 0053 - nothing to do"; Write-Host ""; Write-Host "######## DONE (upgrade: already 0053)"; exit 0 }
  if ($a -ne '0052') { Stop-Step DB "alembic is '$a', expected 0052" }
  $pgbin = Split-Path $psql
  $out = Join-Path $Keep ("icb_pre_0053_{0}.dump" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
  Write-Host "== checked backup -> $out"
  & "$pgbin\pg_dump.exe" -Fc -f $out -d $pgUrl
  if ($LASTEXITCODE -ne 0) { if (Test-Path $out) { Rename-Item $out "$out.FAILED" }; Stop-Step BACKUP "pg_dump exited $LASTEXITCODE - nothing upgraded" }
  $list = & "$pgbin\pg_restore.exe" -l $out
  foreach ($t in 'alembic_version', 'trailer_groups', 'trailer_types', 'calculations', 'bill_of_materials') {
    if (-not ($list | Select-String -SimpleMatch "TABLE DATA icb_costings $t ")) { Rename-Item $out "$out.FAILED"; Stop-Step BACKUP "the dump holds no $t data - nothing upgraded" }
  }
  Write-Host "   ok   backup $((Get-Item $out).Length) bytes  sha256 $((Get-FileHash -Algorithm SHA256 $out).Hash.ToLower())"
  Write-Host "== alembic upgrade 0053"
  Push-Location "$Repo\backend"
  & $Py -m alembic upgrade 0053
  $rc = $LASTEXITCODE
  Pop-Location
  if ($rc -ne 0) { Stop-Step UPGRADE "alembic exited $rc - the backup is $out" }
  $a = Get-Alembic
  $env:PGOPTIONS = '-c default_transaction_read_only=on'
  $col = ("" + (& $psql -XAtc "select count(*) from information_schema.columns where table_schema='icb_costings' and table_name='trailer_groups' and column_name='insulation_rule'" $pgUrl)).Trim()
  Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
  Write-Host "== read back: alembic $a; insulation_rule column: $(if ($col -eq '1') { 'present' } else { 'MISSING' })"
  if ($a -ne '0053' -or $col -ne '1') { Stop-Step READBACK "not at 0053 with the column - the backup is $out" }
  Write-Host ""; Write-Host "######## DONE (upgrade: 0052 -> 0053, read back) - start :8000 again, then tell the CA"; exit 0
}

$tool = "$Repo\ops\prod-rt6\rt6_rules.py"
if (-not (Test-Path $tool)) { Stop-Step KIT "no $tool - the main clone is not at v1.61.0" }
if ((Get-Alembic) -ne '0053') { Stop-Step DB "alembic is not 0053 - run -Step upgrade first" }
switch ($Step) {
  'rules-dryrun' { & $Py $tool --target dev }
  'rules-show'   { & $Py $tool --target dev --show }
  'rules-apply'  { $o = Join-Path $Keep 'rt6-dev-rules'; New-Item -ItemType Directory -Force $o | Out-Null; & $Py $tool --target dev --apply --out-dir $o }
}
$rc = $LASTEXITCODE
Write-Host ""
if ($rc -ne 0) { Stop-Step RULES "rt6_rules.py exited $rc" }
Write-Host "######## DONE ($Step) - tell the CA"
