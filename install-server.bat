@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\bootstrap.ps1" -Role Server
if errorlevel 1 (
    pause
    exit /b 1
)
exit /b 0
