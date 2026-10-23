# RT11 - run the paste block of docs/runbooks/prod-check-rt11.md from WINDOWS POWERSHELL 5.1, as Michael pastes it,
# against a fake prod in WSL (Michael's rule: every block run in the sim from PS 5.1 first). RT10's tested sim
# (ops/prod-rt10/sim/ps51/run_block.ps1), its names changed; the fake prod lives in the Ubuntu 24.04 clone of prod
# (the WSL distro $Distro) and the stub is RT11's copy of RT9's, which names that distro (and refuses without it).
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\ops\prod-rt11\sim\ps51\run_block.ps1"
#
# 1. compiles RT9's stub.cs into ssh.exe + scp.exe (native, so PS 5.1 hands them arguments exactly as it hands the
#    real ssh) and puts them FIRST on PATH; refuses unless both resolve to the stubs (fail closed);
# 2. brings up the fake prod (fakeprod_up.sh up) and copies the REAL stage (mkstage_check.sh's output) to a temp
#    folder, where run_check.ps1's ONE host line is pointed at stubuser@127.0.0.9 (nothing else changes);
# 3. reads the runbook's block and runs its line - the runbook's text, only the stage folder swapped - as a paste
#    into a NEW Windows PowerShell 5.1, and checks its exit code, its first line and its last ######## line against
#    the runbook's own words, the report in the sim's Downloads, and the fake prod's /tmp empty afterwards;
# 4. negative controls: the wrong machine (STOP, still clean), the VPN down, a tampered kit (STOP before any ssh),
#    the stub without its settings;
# 5. checks Michael's clone is untouched (its untracked list) and removes the sim.
$ErrorActionPreference = 'Continue'
if ($PSVersionTable.PSVersion.Major -ne 5) { Write-Host "run this under Windows PowerShell 5.1 (powershell.exe), not $($PSVersionTable.PSVersion)"; exit 2 }
$Repo      = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$Runbook   = Join-Path $Repo 'docs\runbooks\prod-check-rt11.md'
$StubSrc   = Join-Path $Repo 'ops\prod-rt11\sim\ps51\stub.cs'
$Distro    = 'icb-noble-rt11'   # the Ubuntu 24.04 clone of prod (the WSL sims' distro)
$RealStage = 'C:\Users\micge\Documents\icb-rt11-stage\check'
$Work      = Join-Path $env:TEMP ("rt11ps51-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$Stage     = Join-Path $Work 'check'
$Req       = Join-Path $Work 'req'
$StubDir   = Join-Path $Work 'stub'
$Home2     = Join-Path $Work 'home'
New-Item -ItemType Directory -Force -Path $Req, $StubDir, (Join-Path $Home2 'Downloads') | Out-Null
Set-Location $Work            # never Michael's clone: a child powershell.exe once wrote a cache into the folder it started in
$Clone = 'C:\Users\micge\Documents\icb-platform'
function Untracked() { $env:GIT_OPTIONAL_LOCKS = '0'; @(& git -C $Clone status --porcelain=v1 -uall 2>$null | Where-Object { $_ -like '`?`? *' }) }
$UntrackedBefore = Untracked
function WslPath($p) { $f = [System.IO.Path]::GetFullPath($p); '/mnt/' + $f.Substring(0,1).ToLower() + $f.Substring(2).Replace('\', '/') }
$FakeSh = WslPath (Join-Path $PSScriptRoot 'fakeprod_up.sh')
function Fake([string[]]$a) { @(& wsl.exe -d $Distro -u root -- bash $FakeSh @a 2>&1 | ForEach-Object { "$_" }) }
$Script:Pass = 0; $Script:Fail = 0
function Ok($m)  { $Script:Pass++; Write-Host "  ok    $m" }
function Bad($m) { $Script:Fail++; Write-Host "  FAIL  $m" }
function Quit($m) { Write-Host "######## SIM STOP: $m"; Fake @('down') | Out-Null; exit 2 }

# A paste = the text typed into a NEW Windows PowerShell 5.1 window: the text goes into a .ps1 that powershell.exe runs
# with -File (the same parser as the prompt), plus one line to read the exit code as Michael reads it on screen.
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

Write-Host "== PS $($PSVersionTable.PSVersion) on $env:COMPUTERNAME; stage $RealStage; work $Work"
if (-not (Test-Path (Join-Path $RealStage 'run_check.ps1'))) { Quit "no stage at $RealStage (mkstage_check.sh first)" }
# ---- 1. the stubs -------------------------------------------------------------------------------------------------
Add-Type -TypeDefinition (Get-Content -Raw -Path $StubSrc) -Language CSharp -OutputAssembly (Join-Path $StubDir 'ssh.exe') -OutputType ConsoleApplication
Copy-Item (Join-Path $StubDir 'ssh.exe') (Join-Path $StubDir 'scp.exe')

# ---- 2. the fake prod and the stage copy ----------------------------------------------------------------------------
$upOut = Fake @('up'); $upOut | ForEach-Object { Write-Host "   $_" }
if (-not ($upOut | Where-Object { $_ -match '^SIM=' })) { Quit "the fake prod did not come up" }
Copy-Item -Recurse $RealStage $Stage
$hostLine = "`$Vm     = 'mickeyger@192.168.0.251'"
$rc1 = Join-Path $Stage 'run_check.ps1'
$orig = [System.IO.File]::ReadAllText($rc1)
if (([regex]::Matches($orig, '192\.168\.0\.251')).Count -ne 1 -or -not $orig.Contains($hostLine)) { Quit "run_check.ps1: the one host line was not found exactly once" }
[System.IO.File]::WriteAllText($rc1, $orig.Replace($hostLine, "`$Vm     = 'stubuser@127.0.0.9'"), (New-Object System.Text.ASCIIEncoding))
Ok "the REAL stage copied; its ONE host line pointed at stubuser@127.0.0.9 (nothing else changed)"
$env:PATH = "$StubDir;$env:PATH"
$env:RT9_STUB_REQ = $Req
$env:RT11_STUB_DISTRO = $Distro
$env:RT9_STUB_FWD = WslPath (Join-Path $PSScriptRoot 'forward.sh')
$env:USERPROFILE = $Home2           # the line writes to <USERPROFILE>\Downloads: the sim's, never Michael's
$resolved = Invoke-Paste '(Get-Command ssh).Source; (Get-Command scp).Source' 'stubs-resolve'
if (@($resolved | Where-Object { $_ -like "$StubDir*" }).Count -ne 2) { Quit "ssh/scp do not resolve to the stubs: $resolved" }
Ok "ssh and scp resolve to the stubs in a fresh powershell.exe"

# ---- 3. the runbook's block -----------------------------------------------------------------------------------------
$md = [System.IO.File]::ReadAllText($Runbook, [System.Text.Encoding]::UTF8)
$rx = 'PASTE INTO: (?<win>[^\r\n]+)\r?\n```\r?\n(?<cmd>[^\r\n]+)\r?\n```\r?\nFIRST LINE YOU SHOULD SEE: (?<first>[^\r\n]+)\r?\nIT WILL ASK FOR: (?<asks>[^\r\n]+)\r?\nWHEN IT ENDS: (?<ends>[^\r\n]+)\r?\nIF YOU SEE "STOP": (?<stop>[^\r\n]+)'
$blocks = @([regex]::Matches($md, $rx))
if ($blocks.Count -ne 1) { Quit "the runbook has $($blocks.Count) paste blocks, expected 1" }
$b = $blocks[0]
$cmd = $b.Groups['cmd'].Value
if ($cmd -match '[^\x20-\x7e]' -or $cmd -match '<[a-z]+>' -or -not $cmd.Contains($RealStage)) { Bad "the block's line is not plain ASCII naming the stage: $cmd" } else { Ok "the block's line is plain printable ASCII, no placeholder, the stage's full path" }
$ell = [string][char]0x2026; $arr = [string][char]0x2192
function Cut($s) { foreach ($m in @(" $ell", " $arr", $ell, $arr)) { $i = $s.IndexOf($m); if ($i -ge 0) { $s = $s.Substring(0, $i) } }; $s.TrimEnd() }
$WantFirst = Cut $b.Groups['first'].Value; $WantEnd = Cut $b.Groups['ends'].Value
$Paste = $cmd.Replace($RealStage, $Stage)
function Check-Run($label, $out, [int]$wantRc, $endWant) {
  $first = ($out | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
  $last = ($out | Where-Object { $_ -like '########*' } | Select-Object -Last 1)
  $okF = "$first".StartsWith($WantFirst.Substring(0, [Math]::Min($WantFirst.Length, 40)))
  $m = "$label`: exit $Script:LastRc; first '$first'; last '$last'"
  if ($Script:LastRc -eq $wantRc -and $okF -and "$last".StartsWith($endWant)) { Ok $m; return $true }
  Bad $m; $out | Select-Object -Last 30 | ForEach-Object { Write-Host "        | $_" }; return $false
}

Write-Host "== the block, as pasted (apt, pip and fontconfig are the 24.04 clone's real answers; the roles and bodies the fixture's)"
$out = Invoke-Paste $Paste 'block'
$first = ($out | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
if ("$first".StartsWith($WantFirst)) { Ok "first line = the runbook's FIRST LINE ($first)" } else { Bad "first line '$first' <> '$WantFirst'" }
[void](Check-Run 'the block' $out 0 $WantEnd)
if ($out -match 'SUMMARY: Ubuntu 24\.04\.\d+ LTS .{1,3} 3\.12\.3 .{1,3} pango 1\.52\.1\S* harfbuzz 8\.3\.0\S* .{1,3} harfbuzz-subset (absent|installed) .{1,3} apt: \d+ new, 0 upgraded .{1,3} pip: \d+ new, 0 changed .{1,3} weasyprint absent .{1,3} quote\.generate: admin\+full\+user \(4 users by role\) .{1,3} bodies with a template: 5 of 7') { Ok "the window carries the SUMMARY: the clone's release, python, libraries, apt and pip; the fixture's roles and bodies" } else { Bad "the SUMMARY line is not the expected shape" }
if ($out -match 'sudo asks for the VM password') { Ok "it says before the sudo prompt that the VM password comes next ($($b.Groups['asks'].Value))" } else { Bad "no VM password line" }
$rep = @(Get-ChildItem (Join-Path $Home2 'Downloads') -Filter 'rt11-check-*.txt')
if ($rep.Count -eq 1 -and (Get-Content $rep[0].FullName -Raw) -match '######## DONE \(read only\)') { Ok "the report reached Downloads ($($rep[0].Name)) and ends DONE" } else { Bad "Downloads holds $($rep.Count) report(s)" }
$left = Fake @('ls')
if ($left.Count -eq 0) { Ok "the fake prod's /tmp is empty after the block (kit, report and helper gone)" } else { Bad "fake /tmp holds: $($left -join ', ')" }
$cmds = Fake @('log')
$want = @('bash /tmp/icb-rt11-vm.sh where', 'bash /tmp/icb-rt11-vm.sh unpack', 'sudo bash /tmp/icb-rt11-check/rt11_check.sh', 'bash /tmp/icb-rt11-vm.sh readback')
if ((($cmds | Select-Object -Last 4) -join '|') -eq ($want -join '|')) { Ok "prod ran exactly the four commands, each a file by path: $($want -join '; ')" } else { Bad "remote commands: $($cmds -join '; ')" }

# ---- 4. negative controls -------------------------------------------------------------------------------------------
Write-Host "== negative controls"
Fake @('hostname', 'icb-mes-dev') | Out-Null
$out = Invoke-Paste $Paste 'nc-wrong-machine'
if ($Script:LastRc -eq 1 -and ($out -match "STOP \[WHERE\]: ssh stubuser@127.0.0.9 reached 'icb-mes-dev', not icb-mes-prod")) { Ok "the wrong machine: STOP [WHERE] on the first line's check, exit 1" } else { Bad "wrong machine: exit $Script:LastRc $out" }
# only the helper reached that machine (it is how the line learns where it is); the kit never left the laptop
$left = Fake @('ls'); if (($left -join ',') -eq 'icb-rt11-vm.sh') { Ok "the wrong machine got the helper only, never the kit" } else { Bad "after the wrong machine: $($left -join ', ')" }
Fake @('state', 'x', 'off') | Out-Null
Fake @('hostname', 'icb-mes-prod') | Out-Null
$env:RT9_STUB_DOWN = '1'
$out = Invoke-Paste $Paste 'nc-vpn-down'
$env:RT9_STUB_DOWN = ''
if ($Script:LastRc -eq 1 -and ($out -match 'STOP \[WHERE\]') -and ($out -match 'connect the VPN')) { Ok "the VPN down: STOP [WHERE] with the VPN hint, exit 1" } else { Bad "VPN down: exit $Script:LastRc $out" }
$T2 = Join-Path $Work 'tampered'; Copy-Item -Recurse $Stage $T2
Add-Content -Path (Join-Path $T2 'icb-rt11-check.tar') -Value 'x'
$before = @(Get-ChildItem $Req -Filter '*.req').Count
$out = Invoke-Paste ($cmd.Replace($RealStage, $T2)) 'nc-tampered'
$calls = @(Get-ChildItem $Req -Filter '*.req').Count - $before
if ($Script:LastRc -eq 1 -and ($out -match 'STOP \[KIT\]') -and $calls -eq 0) { Ok "a tampered kit: STOP [KIT] before any ssh or scp (0 calls), exit 1" } else { Bad "tampered kit: exit $Script:LastRc, $calls call(s): $out" }
$o = Invoke-Paste "`$env:RT11_STUB_DISTRO=''; & ssh stubuser@127.0.0.9 'echo x'; `"rc=`$LASTEXITCODE`"" 'nc-stub-unset'
if (($o -match 'rc=255') -and ($o -match 'refusing')) { Ok "the stub without RT11_STUB_DISTRO refuses (exit 255): fail closed, never the default distro" } else { Bad "stub fail-closed: $o" }

# ---- 5. Michael's clone, then remove the sim -------------------------------------------------------------------------
$new = @(Compare-Object $UntrackedBefore (Untracked) | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" })
if ($new.Count -eq 0) { Ok "Michael's clone: the untracked list is the same before and after ($(@($UntrackedBefore).Count) entries)" } else { Bad "Michael's clone changed: $($new -join '; ')" }
Fake @('down') | ForEach-Object { Write-Host "   $_" }
Write-Host ""
Write-Host "== $Script:Pass passed, $Script:Fail failed (pastes and their output: $Work)"
if ($Script:Fail -gt 0) { exit 1 } else { exit 0 }
