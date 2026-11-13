# RT11 - run install_venv.ps1 from WINDOWS POWERSHELL 5.1 against a THROW-AWAY copy of a clone (never Michael's):
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\ops\prod-rt11\laptop\sim_install_venv.ps1"
#
# A scratch "clone" under %TEMP%: this worktree's backend\app + requirements.txt, and a fresh venv with the base
# requirements minus WeasyPrint (Michael's venv before the block). Then: the line before the merge (no pin: STOP [CODE], nothing
# installed); the line (DONE, the gate True); the line again ("already installed"). Michael's clone is checked
# untouched; the scratch folder is removed.
$ErrorActionPreference = 'Continue'
if ($PSVersionTable.PSVersion.Major -ne 5) { Write-Host "run this under Windows PowerShell 5.1"; exit 2 }
$Wt    = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$Line  = Join-Path $PSScriptRoot 'install_venv.ps1'
$Work  = Join-Path $env:TEMP ("rt11venv-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$Fake  = Join-Path $Work 'clone'
New-Item -ItemType Directory -Force -Path (Join-Path $Fake 'backend') | Out-Null
Set-Location $Work
$Clone = 'C:\Users\micge\Documents\icb-platform'
function Untracked() { $env:GIT_OPTIONAL_LOCKS = '0'; @(& git -C $Clone status --porcelain=v1 -uall 2>$null | Where-Object { $_ -like '`?`? *' }) }
$UntrackedBefore = Untracked
$Script:Pass = 0; $Script:Fail = 0
function Ok($m)  { $Script:Pass++; Write-Host "  ok    $m" }
function Bad($m) { $Script:Fail++; Write-Host "  FAIL  $m" }
Copy-Item -Recurse (Join-Path $Wt 'backend\app') (Join-Path $Fake 'backend\app')
Copy-Item (Join-Path $Wt 'backend\requirements.txt') (Join-Path $Fake 'backend\requirements.txt')
& py -3.14 -m venv (Join-Path $Fake 'backend\.venv') 2>&1 | Out-Null
$Py = Join-Path $Fake 'backend\.venv\Scripts\python.exe'
# Michael's venv before the block: the base requirements (cffi, Pillow, jinja2, ... - WeasyPrint's own dependencies
# outside the lock), without WeasyPrint, which is the block's job (--no-deps installs only the lock)
$base = Join-Path $Work 'requirements-base.txt'
[System.IO.File]::WriteAllLines($base, [string[]]@(Get-Content (Join-Path $Wt 'backend\requirements.txt') | Where-Object { $_ -notmatch '^weasyprint==' }))
& $Py -m pip install -q --disable-pip-version-check -r $base 2>&1 | Out-Null
function Run($label) {
  $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Line -Repo $Fake 2>&1 | ForEach-Object { "$_" }
  $Script:Rc = $LASTEXITCODE
  [System.IO.File]::WriteAllLines((Join-Path $Work "$label.log"), [string[]]@($out))
  return ,[string[]]@($out)
}
$req = Join-Path $Fake 'backend\requirements.txt'
$orig = [System.IO.File]::ReadAllText($req)
[System.IO.File]::WriteAllText($req, $orig.Replace("weasyprint==70.0", "# (before the merge)"))
$out = Run 'nc-before-merge'
$n = @(& $Py -m pip list --format=freeze 2>$null | Where-Object { $_ -match '^weasyprint==' }).Count
if ($Script:Rc -eq 1 -and ($out -match 'STOP \[CODE\]') -and $n -eq 0) { Ok "before the merge: STOP [CODE], nothing installed" } else { Bad "before the merge: exit $Script:Rc, weasyprint rows $n" }
[System.IO.File]::WriteAllText($req, $orig)
$out = Run 'line'
$first = ($out | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1); $last = ($out | Where-Object { $_ -like '########*' } | Select-Object -Last 1)
if ($Script:Rc -eq 0 -and "$first".StartsWith('######## RT11 laptop venv . ') -and "$last".StartsWith('######## DONE - WeasyPrint 70.0 in the :8000 venv; the gate reads True.') -and ($out -match 'the gate with the clone.s code reads True')) { Ok "the line: DONE; the venv gained exactly the lock; weasyprint 70.0; the gate True" } else { Bad "the line: exit $Script:Rc; last '$last'"; $out | Select-Object -Last 15 | ForEach-Object { Write-Host "        | $_" } }
$out = Run 'again'
if ($Script:Rc -eq 0 -and ($out -match 'already installed at its version: nothing to do')) { Ok "again: already installed, nothing done" } else { Bad "again: exit $Script:Rc" }
$new = @(Compare-Object $UntrackedBefore (Untracked) | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" })
if ($new.Count -eq 0) { Ok "Michael's clone: the untracked list is the same before and after" } else { Bad "Michael's clone changed: $($new -join '; ')" }
Set-Location $env:TEMP
Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "== $Script:Pass passed, $Script:Fail failed"
if ($Script:Fail -gt 0) { exit 1 } else { exit 0 }
