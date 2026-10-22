# RT9 - run every paste block of docs/runbooks/prod-deploy-v1.62.0.md from WINDOWS POWERSHELL 5.1, as Michael pastes
# them, against a fake prod in WSL (Michael's rule, RT9 dispatch: every block run in the sim from PS 5.1 first).
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\ops\prod-release-v1.62.0\sim\ps51\run_blocks.ps1" [-Kit rt9/release-v1.62.0]
#
# 1. compiles stub.cs into ssh.exe + scp.exe (native, so PS 5.1 hands them arguments exactly as it hands the real ssh)
#    and puts them FIRST on PATH; refuses unless both resolve to the stubs (fail closed: RT7's 16 Oct slip);
# 2. brings up the fake prod (fakeprod_up.sh: the REAL mkstage_window.sh stages the window from the kit branch) and
#    copies the stage to a temp folder, where window_common.ps1's ONE host line is pointed at stubuser@127.0.0.9;
# 3. reads the runbook's blocks (PASTE INTO / the fenced line / FIRST LINE / IT WILL ASK FOR / WHEN IT ENDS / STOP)
#    and runs each window block's line - the runbook's text, only the stage folder swapped - as a paste into a NEW
#    Windows PowerShell 5.1 window, and checks its exit code, its first line and its last ######## line against the
#    runbook's own words; runs the :8000 health line for real (a read-only GET of Michael's dev server);
# 4. negative controls: RT8's quoting fault reproduced through the stub; a wrong step word; the VPN down; a tampered
#    helper; the stub without its settings;
# 5. reports the fake prod's /tmp after the cleanup block and removes the sim (fakeprod_down.sh).
param([string]$Kit = 'rt9/release-v1.62.0')
$ErrorActionPreference = 'Continue'   # PS 5.1 turns a native command's stderr into a terminating error under 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5) { Write-Host "run this under Windows PowerShell 5.1 (powershell.exe), not $($PSVersionTable.PSVersion)"; exit 2 }
$Repo      = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$Runbook   = Join-Path $Repo 'docs\runbooks\prod-deploy-v1.62.0.md'
$RealStage = 'C:\Users\micge\Documents\icb-rt9-stage\window'
$Work      = Join-Path $env:TEMP ("rt9ps51-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$Stage     = Join-Path $Work 'stage\window'
$Req       = Join-Path $Work 'req'
$StubDir   = Join-Path $Work 'stub'
$Home2     = Join-Path $Work 'home'
New-Item -ItemType Directory -Force -Path $Stage, $Req, $StubDir, (Join-Path $Home2 'Downloads') | Out-Null
# Every paste runs FROM the work folder: a child powershell.exe here once wrote its ModuleAnalysisCache to a relative
# path in the folder it was started from (21 Oct: Michael's main clone). The clone's untracked list is read before
# and after (read only) and must not change.
Set-Location $Work
$Clone = 'C:\Users\micge\Documents\icb-platform'
function Untracked() { $env:GIT_OPTIONAL_LOCKS = '0'; @(& git -C $Clone status --porcelain=v1 -uall 2>$null | Where-Object { $_ -like '`?`? *' }) }
$UntrackedBefore = Untracked
function WslPath($p) { $f = [System.IO.Path]::GetFullPath($p); '/mnt/' + $f.Substring(0,1).ToLower() + $f.Substring(2).Replace('\', '/') }
$Script:Pass = 0; $Script:Fail = 0
function Ok($m)  { $Script:Pass++; Write-Host "  ok    $m" }
function Bad($m) { $Script:Fail++; Write-Host "  FAIL  $m" }
function Quit($m) { Write-Host "######## SIM STOP: $m"; & wsl.exe -u root -- bash (WslPath (Join-Path $PSScriptRoot 'fakeprod_down.sh')) 2>&1 | Out-Null; exit 2 }

# A paste = the text typed into a NEW Windows PowerShell 5.1 window: the text goes into a .ps1 that powershell.exe runs
# with -File (the same parser as the interactive prompt, no second layer of native-argument quoting), plus one line
# the sim adds to read the result as Michael reads it on screen: the exit code of the last command.
$Script:N = 0
function Invoke-Paste([string]$text, [string]$label) {
  $Script:N++
  $f = Join-Path $Work ('paste-{0:d2}-{1}.ps1' -f $Script:N, ($label -replace '[^a-zA-Z0-9]+', '-'))
  [System.IO.File]::WriteAllText($f, $text + "`r`nexit `$LASTEXITCODE`r`n", (New-Object System.Text.ASCIIEncoding))
  $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f 2>&1 | ForEach-Object { "$_" }
  $Script:LastRc = $LASTEXITCODE
  [System.IO.File]::WriteAllLines(($f -replace '\.ps1$', '.log'), [string[]]@($out))
  return ,[string[]]@($out)
}

Write-Host "== PS $($PSVersionTable.PSVersion) on $env:COMPUTERNAME; kit $Kit; work $Work"
# ---- 1. the stubs -------------------------------------------------------------------------------------------------
$src = Get-Content -Raw -Path (Join-Path $PSScriptRoot 'stub.cs')
Add-Type -TypeDefinition $src -Language CSharp -OutputAssembly (Join-Path $StubDir 'ssh.exe') -OutputType ConsoleApplication
Copy-Item (Join-Path $StubDir 'ssh.exe') (Join-Path $StubDir 'scp.exe')

# ---- 2. the fake prod ---------------------------------------------------------------------------------------------
$up = & wsl.exe -u root -- bash (WslPath (Join-Path $PSScriptRoot 'fakeprod_up.sh')) $Kit (WslPath $Stage) 2>&1 | ForEach-Object { "$_" }
$up | ForEach-Object { Write-Host "   $_" }
$simLine = $up | Where-Object { $_ -match '^SIM=' } | Select-Object -First 1
if (-not $simLine) { Quit "the fake prod did not come up" }
$Sim = $simLine.Substring(4).Trim()
$Fwd = "$Sim/work/ops/prod-release-v1.62.0/sim/ps51/forward.sh"
$wc = Join-Path $Stage 'window_common.ps1'
$orig = [System.IO.File]::ReadAllText($wc)
$hostLine = "`$Vm     = 'mickeyger@192.168.0.251'"
if (([regex]::Matches($orig, '192\.168\.0\.251')).Count -ne 1 -or -not $orig.Contains($hostLine)) { Quit "window_common.ps1: the one host line was not found exactly once" }
[System.IO.File]::WriteAllText($wc, $orig.Replace($hostLine, "`$Vm     = 'stubuser@127.0.0.9'"), (New-Object System.Text.ASCIIEncoding))
Ok "stage copied from the real mkstage_window.sh; the ONE host line pointed at stubuser@127.0.0.9 (nothing else changed)"

$env:PATH = "$StubDir;$env:PATH"
$env:RT9_STUB_REQ = $Req
$env:RT9_STUB_FWD = $Fwd
$env:USERPROFILE = $Home2           # the fetch line writes to <USERPROFILE>\Downloads: the sim's, never Michael's
$resolved = Invoke-Paste '(Get-Command ssh).Source; (Get-Command scp).Source' 'stubs-resolve'
if (@($resolved | Where-Object { $_ -like "$StubDir*" }).Count -ne 2) { Quit "ssh/scp do not resolve to the stubs: $resolved" }
Ok "ssh and scp resolve to the stubs in a fresh powershell.exe ($($resolved -join ', '))"

# ---- 3. the runbook's blocks ----------------------------------------------------------------------------------------
$md = [System.IO.File]::ReadAllText($Runbook, [System.Text.Encoding]::UTF8)
$rx = 'PASTE INTO: (?<win>[^\r\n]+)\r?\n```\r?\n(?<cmd>[^\r\n]+)\r?\n```\r?\nFIRST LINE YOU SHOULD SEE: (?<first>[^\r\n]+)\r?\nIT WILL ASK FOR: (?<asks>[^\r\n]+)\r?\nWHEN IT ENDS: (?<ends>[^\r\n]+)\r?\nIF YOU SEE "STOP": (?<stop>[^\r\n]+)'
$blocks = @([regex]::Matches($md, $rx))
Write-Host "== the runbook has $($blocks.Count) paste blocks"
$ell = [string][char]0x2026; $arr = [string][char]0x2192
function Cut($s) { foreach ($m in @(" $ell", " $arr", $ell, $arr)) { $i = $s.IndexOf($m); if ($i -ge 0) { $s = $s.Substring(0, $i) } }; $s.TrimEnd() }
$bad = @($blocks | Where-Object { $_.Groups['cmd'].Value -match '[^\x20-\x7e]' -or $_.Groups['cmd'].Value -match '<[a-z]+>' })
if ($bad.Count -eq 0 -and $blocks.Count -gt 0) { Ok "every block's command line is plain printable ASCII with no <placeholder> ($($blocks.Count) blocks)" } else { Bad "blocks with non-ASCII or a placeholder: $($bad | ForEach-Object { $_.Groups['cmd'].Value })" }

function Run-Block($b, $label, [int]$wantRc = 0) {
  $cmd = $b.Groups['cmd'].Value.Replace($RealStage, $Stage)
  $before = @(Get-ChildItem $Req -Filter '*.req').Count
  $out = Invoke-Paste $cmd $label
  $rc = $Script:LastRc
  $first = ($out | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
  $last = ($out | Where-Object { $_ -like '########*' } | Select-Object -Last 1)
  $wf = Cut $b.Groups['first'].Value; $we = Cut $b.Groups['ends'].Value
  $calls = @(Get-ChildItem $Req -Filter '*.req').Count - $before
  $okRc = ($rc -eq $wantRc); $okF = ("$first".StartsWith($wf)); $okE = ("$last".StartsWith($we))
  $m = "block '$label': exit $rc, $calls ssh/scp call(s); first line $(if ($okF) {'= the runbook'} else {"'$first' <> '$wf'"}); end $(if ($okE) {'= the runbook'} else {"'$last' <> '$we'"})"
  if ($okRc -and $okF -and $okE) { Ok $m } else { Bad $m; $out | Select-Object -Last 25 | ForEach-Object { Write-Host "        | $_" } }
}

$win = @($blocks | Where-Object { $_.Groups['cmd'].Value -like "*$RealStage*" })
$byStep = @{}
foreach ($b in $win) {
  $c = $b.Groups['cmd'].Value
  $k = if ($c -match 'run_window_step\.ps1" (\S+)$') { $Matches[1] } elseif ($c -match 'run_window_(\w+)\.ps1"$') { $Matches[1] } else { '?' }
  $byStep[$k] = $b
}
$order = 'copy', 'preflight', 'all-before', 'deploy', 'all-after', 'doors', 'verify', 'fetch', 'cleanup'
foreach ($k in $order) { if (-not $byStep.ContainsKey($k)) { Bad "the runbook has no block for '$k'" } }
if ($win.Count -eq $order.Count) { Ok "the runbook has exactly the $($order.Count) window blocks ($($order -join ', '))" } else { Bad "the runbook has $($win.Count) window blocks, expected $($order.Count)" }

# the :8000 health line runs for real (a read-only GET of Michael's dev server); the start.bat line only names his script
$h = @($blocks | Where-Object { $_.Groups['cmd'].Value -like '*127.0.0.1:8000/health/version*' })
if ($h.Count -eq 1) {
  $o = (Invoke-Paste $h[0].Groups['cmd'].Value '8000-health') -join ''
  if ($o -match '^\{"version":"v1\.6\d\.\d+","environment":"unset"\}$') { Ok ":8000 health line runs in PS 5.1 and prints one JSON line ($o)" } else { Bad ":8000 health line printed '$o'" }
} else { Bad "the runbook has $($h.Count) :8000 health blocks, expected 1" }
$s = @($blocks | Where-Object { $_.Groups['cmd'].Value -like '*scripts\start.bat*' })
if ($s.Count -eq 1 -and $s[0].Groups['cmd'].Value -eq '"C:\Users\micge\Documents\icb-platform\scripts\start.bat"' -and (Test-Path 'C:\Users\micge\Documents\icb-platform\scripts\start.bat')) {
  Ok ":8000 start line names Michael's own start.bat by its full path (it exists; not run here: :8000 is Michael's)"
} else { Bad "the :8000 start block is missing or not the one quoted path" }

Write-Host "== the window, in order (the page's All and the N10022 check are browser steps: nothing to paste)"
foreach ($k in $order) { if ($byStep.ContainsKey($k)) { Run-Block $byStep[$k] $k } }
$tar = Get-ChildItem (Join-Path $Home2 'Downloads') -Filter 'rt9-window-back-*.tar' | Select-Object -First 1
if ($tar) {
  $members = @(& tar.exe -tf $tar.FullName | Where-Object { $_ -match '^[^/]+/out-[^/]+/$' })
  $rt7 = @($members | Where-Object { $_ -match '20261020' })
  $want = 'icb-release-v1.62.0/out-preflight-', 'icb-release-v1.62.0/out-deploy-', 'icb-release-v1.62.0/out-verify-', 'icb-rt2-all/out-pre-', 'icb-rt2-all/out-post-', 'icb-rt2-doors/out-'
  $miss = @($want | Where-Object { $w = $_; -not ($members | Where-Object { $_.StartsWith($w) }) })
  if ($miss.Count -eq 0 -and $rt7.Count -eq 0) { Ok "the fetched tar holds this window's out folders ($($members.Count)) and none of RT7's 20 Oct ones" } else { Bad "fetched tar: missing $($miss -join ', '); RT7's: $($rt7 -join ', ')" }
} else { Bad "no rt9-window-back-*.tar in the sim's Downloads" }

# ---- 4. negative controls -------------------------------------------------------------------------------------------
Write-Host "== the fake prod's /tmp after the cleanup block, and negative controls"
$down = @(& wsl.exe -u root -- bash (WslPath (Join-Path $PSScriptRoot 'fakeprod_down.sh')) report-only 2>&1 | ForEach-Object { "$_" })
$listing = @(); $inTmp = $false
foreach ($l in $down) { if ($l -like '== fake prod /tmp*') { $inTmp = $true; continue }; if ($l -like '==*') { $inTmp = $false }; if ($inTmp) { $listing += $l.Trim() } }
# icb-deploy.sh (the repo's deploy script) writes /tmp/icb-rollback-<ts>.txt on EVERY deploy, as on 20 Oct: its own
# record, not a kit; the cleanup leaves it, and this check names it rather than counting it
$rollback = @($listing | Where-Object { $_ -match '^icb-rollback-\d{8}-\d{6}\.txt$' })
$left = @($listing | Where-Object { ($_ -like 'icb-*' -or $_ -like 'rt9-*') -and $_ -notmatch '^icb-rollback-\d{8}-\d{6}\.txt$' })
if ($left.Count -eq 0 -and $rollback.Count -eq 1) { Ok "after the cleanup block the fake prod's /tmp holds no kit name; only icb-deploy.sh's own $($rollback[0]) (every deploy writes one)" } else { Bad "names left in the fake /tmp: $($left -join ', ') (rollback records: $($rollback.Count))" }
# a. RT8's fault, in cleanup_check.ps1 v1's exact shape: a here-string with double quotes inside, as ONE ssh argument
$nc = Invoke-Paste ("`$remote = @'`r`nbash -c 'set -u; echo `"######## NC ran`"; echo second'`r`n'@`r`n& ssh -o BatchMode=yes stubuser@127.0.0.9 `$remote") 'nc-rt8-v1-shape'
$got = Get-ChildItem $Req -Filter 'ssh-*.req.cmdline' | Sort-Object LastWriteTime | Select-Object -Last 1 | ForEach-Object { [System.IO.File]::ReadAllText($_.FullName) }
if (-not ($nc -match 'NC ran') -and -not ($nc -match 'second') -and $Script:LastRc -eq 0) { Ok "RT8's fault reproduced: exit 0 and the inline double-quoted ssh argument ran nothing (ssh received: $got)" } else { Bad "the NC printed: $nc (exit $Script:LastRc)" }
$pc = Invoke-Paste "& ssh -o BatchMode=yes stubuser@127.0.0.9 'echo plain-words-ran'" 'pc-plain-arg'
if ($pc -match 'plain-words-ran') { Ok "positive control: a plain argument (no inner double quotes) runs" } else { Bad "the positive control printed: $pc" }
# b. a wrong step word
$o = Invoke-Paste "powershell -NoProfile -ExecutionPolicy Bypass -File `"$Stage\run_window_step.ps1`" deplyo" 'nc-step-word'
if ($Script:LastRc -eq 1 -and ($o -match 'STOP \[STEP\]')) { Ok "a wrong step word: STOP [STEP], exit 1, nothing run" } else { Bad "wrong step word: exit $Script:LastRc $o" }
# c. the VPN down
$env:RT9_STUB_DOWN = '1'
$o = Invoke-Paste "powershell -NoProfile -ExecutionPolicy Bypass -File `"$Stage\run_window_copy.ps1`"" 'nc-vpn-down'
$env:RT9_STUB_DOWN = ''
if ($Script:LastRc -eq 1 -and ($o -match 'STOP \[WHERE\]') -and ($o -match 'connect the VPN')) { Ok "the VPN down: STOP [WHERE] with the VPN hint, exit 1" } else { Bad "VPN down: exit $Script:LastRc $o" }
# d. a tampered helper
$T2 = Join-Path $Work 'tampered'; Copy-Item -Recurse $Stage $T2
Add-Content -Path (Join-Path $T2 'rt9_vm.sh') -Value 'echo tampered'
$o = Invoke-Paste "powershell -NoProfile -ExecutionPolicy Bypass -File `"$T2\run_window_step.ps1`" verify" 'nc-tampered'
if ($Script:LastRc -eq 1 -and ($o -match 'STOP \[KIT\]')) { Ok "a tampered rt9_vm.sh: STOP [KIT] before any ssh, exit 1" } else { Bad "tampered helper: exit $Script:LastRc $o" }
# e. the stub without its settings refuses (fail closed)
$o = Invoke-Paste "`$env:RT9_STUB_REQ=''; & ssh stubuser@127.0.0.9 'echo x'; `"rc=`$LASTEXITCODE`"" 'nc-stub-unset'
if (($o -match 'rc=255') -and ($o -match 'refusing')) { Ok "the stub without RT9_STUB_REQ refuses (exit 255)" } else { Bad "stub fail-closed: $o" }

$new = @(Compare-Object $UntrackedBefore (Untracked) | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" })
if ($new.Count -eq 0) { Ok "Michael's clone: the untracked list is the same before and after the run ($(@($UntrackedBefore).Count) entries)" } else { Bad "Michael's clone changed: $($new -join '; ')" }

# ---- 5. report + remove ---------------------------------------------------------------------------------------------
$down | ForEach-Object { Write-Host "   $_" }
& wsl.exe -u root -- bash (WslPath (Join-Path $PSScriptRoot 'fakeprod_down.sh')) 2>&1 | Select-Object -Last 1 | ForEach-Object { Write-Host "   $_" }
Write-Host ""
Write-Host "== $Script:Pass passed, $Script:Fail failed (pastes and their output: $Work)"
if ($Script:Fail -gt 0) { exit 1 } else { exit 0 }
