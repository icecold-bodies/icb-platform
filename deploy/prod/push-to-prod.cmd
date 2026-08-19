@echo off
REM ICB MES - deploy to production. Works from cmd.exe, which cannot run a .ps1
REM directly: typing "Push-ToProd.ps1" at a cmd prompt silently does nothing (cmd
REM has no PowerShell host, so it just hands the file to the shell association).
REM This shim forwards to Windows PowerShell, which every Windows box has.
REM
REM   push-to-prod.cmd -Status
REM   push-to-prod.cmd v1.49.1 -DryRun
REM   push-to-prod.cmd v1.49.1
REM
REM Safe to run from PowerShell too - it is just a batch file.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Push-ToProd.ps1" %*
exit /b %errorlevel%
