# RT6 discovery - the ONE line Michael runs, from PowerShell OR Command Prompt (ASCII only: Windows PowerShell 5.1
# reads a BOM-less file as ANSI):
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt6-stage\discovery\run_discovery.ps1"
#
# It copies the staged kit to prod, runs it
# there over `ssh -t` (sudo asks for your VM password), and fetches the result to Downloads. READ ONLY on prod.
# The FIRST line names this machine, prod's machine, the database and prod's HEAD; it refuses when they are not
# the expected ones. Filled in by mkstage_discovery.sh: __TAR_SHA256__ __STAGED_FROM__ __EXPECT_HEADS__.
$ErrorActionPreference = 'Continue'   # native ssh / scp write to stderr; every exit code is checked by hand
$Here      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Tar       = Join-Path $Here 'icb-rt6-discovery.tar'
$TarSha    = '__TAR_SHA256__'
$Staged    = '__STAGED_FROM__'
$Heads     = '__EXPECT_HEADS__'.Split(' ')
$Vm        = 'mickeyger@192.168.0.251'
$VmName    = 'icb-mes-prod'
$PcName    = 'LAPTOP-DGJ0U6RQ'
$Back      = Join-Path $env:USERPROFILE 'Downloads'
function Stop-Step($tag, $why) { Write-Host ""; Write-Host "######## STOP [$tag]: $why"; Write-Host "######## nothing ran on prod after this point - tell the CA"; exit 1 }

# ---- where am I? (the first line) ---------------------------------------------------------------------------------
$probe = & ssh -o BatchMode=yes -o ConnectTimeout=10 $Vm "hostname -s; git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD" 2>$null
$vmHost = if ($probe) { "$($probe[0])".Trim() } else { '?' }
$vmHead = if ($probe -and $probe.Count -gt 1) { "$($probe[1])".Trim() } else { '?' }
$short  = if ($vmHead.Length -ge 7) { $vmHead.Substring(0, 7) } else { $vmHead }
Write-Host "######## RT6 discovery (read only) . machine $env:COMPUTERNAME -> $vmHost . db icb_platform (checked on the VM) . head $short . stage $($Staged.Substring(0,7)) . $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
if ($env:COMPUTERNAME -ne $PcName) { Stop-Step WHERE "this is $env:COMPUTERNAME; the stage lives on $PcName" }
if ($vmHost -ne $VmName) { Stop-Step WHERE "ssh $Vm reached '$vmHost', not $VmName (VPN up? key loaded?)" }
if ($Heads -notcontains $vmHead) { Stop-Step WHERE "prod's code is $short, this kit expects $(($Heads | ForEach-Object { $_.Substring(0,7) }) -join ' ')" }
if (-not (Test-Path $Tar)) { Stop-Step KIT "no $Tar - re-stage" }
$sha = (Get-FileHash -Algorithm SHA256 $Tar).Hash.ToLower()
if ($sha -ne $TarSha) { Stop-Step KIT "the tar's sha256 is $sha, the stage wrote $TarSha - re-stage" }
Write-Host "== kit ok: icb-rt6-discovery.tar sha256 $($sha.Substring(0,12))..."

# ---- copy, run, fetch ----------------------------------------------------------------------------------------------
Write-Host "== copy the kit to prod /tmp"
& scp -q -o BatchMode=yes $Tar "${Vm}:/tmp/icb-rt6-discovery.tar"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "scp failed (exit $LASTEXITCODE)" }
& ssh -o BatchMode=yes $Vm "cd /tmp && tar -xf icb-rt6-discovery.tar && cd icb-rt6-discovery && sha256sum -c --quiet SHA256SUMS && echo '   unpacked and verified on prod'"
if ($LASTEXITCODE -ne 0) { Stop-Step COPY "the kit did not unpack cleanly on prod (exit $LASTEXITCODE)" }
Write-Host "== run it on prod (sudo asks for your VM password)"
& ssh -t $Vm "sudo bash /tmp/icb-rt6-discovery/rt6_discovery.sh"
$rc = $LASTEXITCODE
if ($rc -ne 0) { Stop-Step RUN "the VM script stopped (exit $rc) - read its STOP line above" }
$last = (& ssh -o BatchMode=yes $Vm "ls -1t /tmp/icb-rt6-discovery/out-*.tar 2>/dev/null | head -n 1") | Select-Object -First 1
if (-not $last) { Stop-Step FETCH "no result tar on prod" }
$dest = Join-Path $Back ("rt6-discovery-back-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".tar")
& scp -q -o BatchMode=yes "${Vm}:$last" $dest
if ($LASTEXITCODE -ne 0) { Stop-Step FETCH "scp back failed (exit $LASTEXITCODE)" }
$bsha = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLower()
Write-Host ""
Write-Host "######## DONE - tell the CA: $dest (sha256 $($bsha.Substring(0,12))...)"
