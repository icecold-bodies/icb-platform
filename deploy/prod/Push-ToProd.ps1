<#
.SYNOPSIS
    Push a release to the ICB MES production VM from Windows.

.DESCRIPTION
    Ships the deploy script from THIS repo over ssh and runs it on the VM with a
    TTY attached, so sudo can prompt for your password. Because the script is
    sent every run, you are always running the version in your working copy —
    prod does not need to have pulled it first.

    Nothing is decided here: all the logic (does this need a migration, a
    frontend build, a restart) lives in icb-deploy.sh and is worked out by
    diffing the deployed commit against the target.

.EXAMPLE
    .\Push-ToProd.ps1 -Status
    What is on prod right now. Read-only.

.EXAMPLE
    .\Push-ToProd.ps1 v1.48.1 -DryRun
    Print the plan — commits, migration/build/restart decisions — and stop.

.EXAMPLE
    .\Push-ToProd.ps1 v1.48.1
    Deploy. Asks on the VM before it changes anything.

.EXAMPLE
    .\Push-ToProd.ps1 -Rollback 0dd4075
    Roll the code back. Never touches the database.
#>
[CmdletBinding(DefaultParameterSetName = 'Deploy')]
param(
    [Parameter(ParameterSetName = 'Deploy', Position = 0, Mandatory = $true)]
    [string]$Tag,

    [Parameter(ParameterSetName = 'Deploy')]
    [switch]$DryRun,

    [Parameter(ParameterSetName = 'Deploy')]
    [switch]$Yes,

    [Parameter(ParameterSetName = 'Deploy')]
    [switch]$ForceRestart,

    [Parameter(ParameterSetName = 'Rollback', Mandatory = $true)]
    [string]$Rollback,

    [Parameter(ParameterSetName = 'Status', Mandatory = $true)]
    [switch]$Status,

    [Parameter(ParameterSetName = 'Status')]
    [switch]$WithDb,

    [string]$Target = 'icb-mes-prod'
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# NB: this writes the remote script's output straight to the host and reports the
# exit code in $script:LastRunCode rather than returning it. A PowerShell
# function returns EVERYTHING written to the output stream, so `return $code`
# would swallow all of ssh's stdout into the return value and the operator would
# see nothing but the two DarkGray progress lines.
$script:LastRunCode = 0

function Send-AndRun {
    param([string]$LocalScript, [string[]]$ScriptArgs, [switch]$NeedsTty)

    $path = Join-Path $here $LocalScript
    if (-not (Test-Path $path)) { throw "missing script: $path" }

    # Normalise CRLF -> LF and ship as base64. A Windows-authored .sh with CRLF
    # dies on the VM with "bad interpreter: \r", and base64 sidesteps every
    # quoting and line-ending hazard in the ssh command line.
    $text = (Get-Content -Raw $path) -replace "`r`n", "`n"
    $b64  = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($text))
    $remote = "/tmp/$([IO.Path]::GetFileNameWithoutExtension($LocalScript))-$(Get-Random).sh"

    Write-Host "→ sending $LocalScript to ${Target}:$remote" -ForegroundColor DarkGray
    & ssh $Target "printf '%s' '$b64' | base64 -d > $remote && chmod +x $remote"
    if ($LASTEXITCODE -ne 0) { throw "could not copy the script to $Target (exit $LASTEXITCODE)" }

    $cmd = (@($remote) + $ScriptArgs) -join ' '
    Write-Host "→ $Target : $cmd`n" -ForegroundColor DarkGray

    # -t forces a TTY so sudo can prompt. mickeyger's sudo is password-required,
    # which is why this cannot run unattended.
    # No Out-Host / no pipeline here: piping breaks the TTY that sudo needs to
    # prompt for a password. The function's output stream reaches the host on its
    # own, provided the caller does not capture it (see the note above).
    if ($NeedsTty) { & ssh -t $Target $cmd } else { & ssh $Target $cmd }
    $script:LastRunCode = $LASTEXITCODE

    & ssh $Target "rm -f $remote" 2>$null | Out-Null
}

switch ($PSCmdlet.ParameterSetName) {

    'Status' {
        $a = @(); if ($WithDb) { $a += '--with-db' }
        Send-AndRun -LocalScript 'icb-status.sh' -ScriptArgs $a -NeedsTty:$WithDb
        exit $script:LastRunCode
    }

    'Rollback' {
        Write-Host "Rolling back production to $Rollback" -ForegroundColor Yellow
        Send-AndRun -LocalScript 'icb-rollback.sh' -ScriptArgs @($Rollback) -NeedsTty
        exit $script:LastRunCode
    }

    'Deploy' {
        # Check the tag is actually on origin before involving the VM — prod
        # fetches from origin, so a tag that only exists locally would fail
        # there with a much less obvious message.
        Push-Location (Split-Path -Parent (Split-Path -Parent $here))
        try {
            $onOrigin = (& git ls-remote --tags origin $Tag) -join ''
            if (-not $onOrigin -and -not ($Tag -match '^[0-9a-f]{7,40}$')) {
                throw "'$Tag' is not a tag on origin. Push it first:  git push origin $Tag"
            }
            if ($onOrigin) {
                $local = (& git rev-parse $Tag 2>$null)
                $remoteSha = ($onOrigin -split '\s+')[0]
                if ($local -and $local -ne $remoteSha) {
                    throw "tag $Tag differs between local ($($local.Substring(0,8))) and origin ($($remoteSha.Substring(0,8))) — resolve before deploying"
                }
                Write-Host "✓ $Tag is on origin" -ForegroundColor Green
            }
        } finally { Pop-Location }

        $a = @($Tag)
        if ($DryRun)       { $a += '--dry-run' }
        if ($Yes)          { $a += '--yes' }
        if ($ForceRestart) { $a += '--force-restart' }

        Send-AndRun -LocalScript 'icb-deploy.sh' -ScriptArgs $a -NeedsTty
        exit $script:LastRunCode
    }
}
