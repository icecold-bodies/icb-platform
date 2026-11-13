# RT11 install kit - run EVERY paste block of docs/runbooks/prod-install-rt11.md from WINDOWS POWERSHELL 5.1, in the
# runbook's order, as Michael pastes them, against a fake prod in the Ubuntu 24.04 clone (Michael's rule: every block
# run in the sim from PS 5.1 first). apt and pip are REAL in the clone; `down` leaves it as found.
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\ops\prod-rt11\install\sim\ps51\run_blocks.ps1" <lane commit>
#
# 1. compiles RT11's stub.cs (ops/prod-rt11/sim/ps51) into ssh.exe + scp.exe, FIRST on PATH; refuses unless both
#    resolve to the stubs (fail closed); the check kit's forward.sh serves this fake prod unchanged;
# 2. brings up the fake prod at <lane commit> and copies the REAL stage (mkstage_install.sh's output), its ONE host
#    line pointed at stubuser@127.0.0.9;
# 3. pastes the runbook's five blocks in order (preflight, apt, pip, verify, rollback) into NEW PS 5.1 windows: each
#    must exit 0, open with its runbook FIRST LINE and end with its WHEN IT ENDS line; its report reaches Downloads;
#    prod ran exactly the four remote commands per step; the fake /tmp is empty after each;
# 4. negative controls: the wrong machine, an unknown step (no ssh at all), a tampered kit (no ssh at all), the stub
#    without its distro;
# 5. checks Michael's clone is untouched (its untracked list) and takes the fake prod down.
param([string]$Lane = '')
$ErrorActionPreference = 'Continue'
if ($PSVersionTable.PSVersion.Major -ne 5) { Write-Host "run this under Windows PowerShell 5.1 (powershell.exe), not $($PSVersionTable.PSVersion)"; exit 2 }
if ($Lane -notmatch '^[0-9a-f]{40}$') { Write-Host "pass the lane commit (40 hex characters)"; exit 2 }
$Repo      = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..')).Path
$Runbook   = Join-Path $Repo 'docs\runbooks\prod-install-rt11.md'
$StubSrc   = Join-Path $Repo 'ops\prod-rt11\sim\ps51\stub.cs'
$FwdSh     = Join-Path $Repo 'ops\prod-rt11\sim\ps51\forward.sh'
$Distro    = 'icb-noble-rt11'
$RealStage = 'C:\Users\micge\Documents\icb-rt11-stage\install'
$Work      = Join-Path $env:TEMP ("rt11ips51-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$Stage     = Join-Path $Work 'install'
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

Write-Host "== PS $($PSVersionTable.PSVersion) on $env:COMPUTERNAME; stage $RealStage; lane $($Lane.Substring(0,7)); work $Work"
if (-not (Test-Path (Join-Path $RealStage 'run_install.ps1'))) { Quit "no stage at $RealStage (mkstage_install.sh first)" }
# ---- 1. the stubs -------------------------------------------------------------------------------------------------
Add-Type -TypeDefinition (Get-Content -Raw -Path $StubSrc) -Language CSharp -OutputAssembly (Join-Path $StubDir 'ssh.exe') -OutputType ConsoleApplication
Copy-Item (Join-Path $StubDir 'ssh.exe') (Join-Path $StubDir 'scp.exe')

# ---- 2. the fake prod and the stage copy ----------------------------------------------------------------------------
$upOut = Fake @('up', $Lane); $upOut | ForEach-Object { Write-Host "   $_" }
if (-not ($upOut | Where-Object { $_ -match '^SIM=' })) { Quit "the fake prod did not come up" }
Copy-Item -Recurse $RealStage $Stage
$hostLine = "`$Vm     = 'mickeyger@192.168.0.251'"
$ri = Join-Path $Stage 'run_install.ps1'
$orig = [System.IO.File]::ReadAllText($ri)
if (([regex]::Matches($orig, '192\.168\.0\.251')).Count -ne 1 -or -not $orig.Contains($hostLine)) { Quit "run_install.ps1: the one host line was not found exactly once" }
[System.IO.File]::WriteAllText($ri, $orig.Replace($hostLine, "`$Vm     = 'stubuser@127.0.0.9'"), (New-Object System.Text.ASCIIEncoding))
Ok "the REAL stage copied; its ONE host line pointed at stubuser@127.0.0.9 (nothing else changed)"
$env:PATH = "$StubDir;$env:PATH"
$env:RT9_STUB_REQ = $Req
$env:RT11_STUB_DISTRO = $Distro
$env:RT9_STUB_FWD = WslPath $FwdSh
$env:USERPROFILE = $Home2           # the line writes to <USERPROFILE>\Downloads: the sim's, never Michael's
$resolved = Invoke-Paste '(Get-Command ssh).Source; (Get-Command scp).Source' 'stubs-resolve'
if (@($resolved | Where-Object { $_ -like "$StubDir*" }).Count -ne 2) { Quit "ssh/scp do not resolve to the stubs: $resolved" }
Ok "ssh and scp resolve to the stubs in a fresh powershell.exe"

# ---- 3. the runbook's blocks, in order ------------------------------------------------------------------------------
$md = [System.IO.File]::ReadAllText($Runbook, [System.Text.Encoding]::UTF8)
$rx = 'PASTE INTO: (?<win>[^\r\n]+)\r?\n```\r?\n(?<cmd>[^\r\n]+)\r?\n```\r?\nFIRST LINE YOU SHOULD SEE: (?<first>[^\r\n]+)\r?\nIT WILL ASK FOR: (?<asks>[^\r\n]+)\r?\nWHEN IT ENDS: (?<ends>[^\r\n]+)\r?\nIF YOU SEE "STOP": (?<stop>[^\r\n]+)'
$blocks = @([regex]::Matches($md, $rx))
$order = @('preflight', 'apt', 'pip', 'verify', 'rollback')
if ($blocks.Count -ne $order.Count) { Quit "the runbook has $($blocks.Count) paste blocks, expected $($order.Count)" }
$ell = [string][char]0x2026; $arr = [string][char]0x2192
function Cut($s) { foreach ($m in @(" $ell", " $arr", $ell, $arr)) { $i = $s.IndexOf($m); if ($i -ge 0) { $s = $s.Substring(0, $i) } }; $s.TrimEnd() }
for ($i = 0; $i -lt $order.Count; $i++) {
  $b = $blocks[$i]; $step = $order[$i]; $cmd = $b.Groups['cmd'].Value
  $want = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$RealStage\run_install.ps1`" $step"
  if ($cmd -ne $want -or $cmd -match '[^\x20-\x7e]') { Bad "block $($i+1) is not the plain ASCII line for '$step': $cmd"; continue }
  $before = @(Fake @('log')).Count
  $out = Invoke-Paste ($cmd.Replace($RealStage, $Stage)) "block-$step"
  $first = ($out | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
  $last = ($out | Where-Object { $_ -like '########*' } | Select-Object -Last 1)
  $wantFirst = Cut $b.Groups['first'].Value; $wantEnd = Cut $b.Groups['ends'].Value
  $rep = @(Get-ChildItem (Join-Path $Home2 'Downloads') -Filter "rt11-install-$step-*.txt")
  $cmds = @(Fake @('log') | Select-Object -Skip $before)
  $wantCmds = @('bash /tmp/icb-rt11-install-vm.sh where', 'bash /tmp/icb-rt11-install-vm.sh unpack', "sudo bash /tmp/icb-rt11-install/rt11_install.sh $step", 'bash /tmp/icb-rt11-install-vm.sh readback')
  $left = @(Fake @('ls'))
  if ($Script:LastRc -eq 0 -and "$first".StartsWith($wantFirst) -and "$last".StartsWith($wantEnd) -and $rep.Count -eq 1 -and (($cmds -join '|') -eq ($wantCmds -join '|')) -and $left.Count -eq 0) {
    Ok "block $($i+1) '$step': exit 0; first line = the runbook's; ends '$wantEnd'; report in Downloads; prod ran the 4 commands by path; /tmp empty"
  } else {
    Bad "block $($i+1) '$step': exit $Script:LastRc; first '$first'; last '$last'; reports $($rep.Count); commands '$($cmds -join '; ')'; /tmp '$($left -join ',')'"
    $out | Select-Object -Last 25 | ForEach-Object { Write-Host "        | $_" }
  }
  if ($step -eq 'verify') {
    if ($out -match '^VERIFY: 10/10 renders correct; gate True$') { Ok "verify, as pasted: 10/10 renders correct; the gate True" } else { Bad "verify's VERIFY line is missing" }
  }
}

# ---- 4. negative controls -------------------------------------------------------------------------------------------
Write-Host "== negative controls"
$pre = $blocks[0].Groups['cmd'].Value
Fake @('hostname', 'icb-mes-dev') | Out-Null
$out = Invoke-Paste ($pre.Replace($RealStage, $Stage)) 'nc-wrong-machine'
Fake @('hostname', 'icb-mes-prod') | Out-Null
$left = @(Fake @('ls'))
if ($Script:LastRc -eq 1 -and ($out -match "STOP \[WHERE\]: ssh stubuser@127.0.0.9 reached 'icb-mes-dev'") -and (($left -join ',') -eq 'icb-rt11-install-vm.sh')) { Ok "the wrong machine: STOP [WHERE] on the first line's check; it got the helper only, never the kit" } else { Bad "wrong machine: exit $Script:LastRc / $($left -join ',')" }
Fake @('down') | Out-Null; $upOut = Fake @('up', $Lane)
foreach ($nc in @(@('nc-unknown-step', ($pre -replace ' preflight$', ' nosuch').Replace($RealStage, $Stage), 'STOP \[STEP\]'),
                  @('nc-tampered', 'TAMPER', 'STOP \[KIT\]'))) {
  $text = $nc[1]
  if ($text -eq 'TAMPER') { $T2 = Join-Path $Work 'tampered'; Copy-Item -Recurse $Stage $T2; Add-Content -Path (Join-Path $T2 'icb-rt11-install.tar') -Value 'x'; $text = $pre.Replace($RealStage, $T2) }
  $calls0 = @(Get-ChildItem $Req -Filter '*.req').Count
  $out = Invoke-Paste $text $nc[0]
  $calls = @(Get-ChildItem $Req -Filter '*.req').Count - $calls0
  if ($Script:LastRc -eq 1 -and ($out -match $nc[2]) -and $calls -eq 0) { Ok "$($nc[0]): $($nc[2].Replace('\','')) before any ssh or scp (0 calls), exit 1" } else { Bad "$($nc[0]): exit $Script:LastRc, $calls call(s)" }
}
$o = Invoke-Paste "`$env:RT11_STUB_DISTRO=''; & ssh stubuser@127.0.0.9 'echo x'; `"rc=`$LASTEXITCODE`"" 'nc-stub-unset'
if (($o -match 'rc=255') -and ($o -match 'refusing')) { Ok "the stub without RT11_STUB_DISTRO refuses (exit 255): fail closed" } else { Bad "stub fail-closed: $o" }

# ---- 5. Michael's clone, then take the fake prod down ----------------------------------------------------------------
$new = @(Compare-Object $UntrackedBefore (Untracked) | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" })
if ($new.Count -eq 0) { Ok "Michael's clone: the untracked list is the same before and after ($(@($UntrackedBefore).Count) entries)" } else { Bad "Michael's clone changed: $($new -join '; ')" }
Fake @('down') | ForEach-Object { Write-Host "   $_" }
Write-Host ""
Write-Host "== $Script:Pass passed, $Script:Fail failed (pastes and their output: $Work)"
if ($Script:Fail -gt 0) { exit 1 } else { exit 0 }
