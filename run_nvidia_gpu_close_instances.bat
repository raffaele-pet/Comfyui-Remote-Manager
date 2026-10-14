@echo off
setlocal EnableExtensions DisableDelayedExpansion
title ComfyUI - PC Server
pushd "%~dp0" || exit /b 1
set "COMFY_PORTABLE_ROOT=%CD%"
set "COMFY_LAUNCHER_FILE=%~f0"

if not exist ".\python_embeded\python.exe" (
    echo ERROR: Place this file in the ComfyUI Portable folder next to python_embeded.
    set "launcher_exit=1"
    goto :finish
)
if not exist ".\ComfyUI\main.py" (
    echo ERROR: ComfyUI\main.py was not found in this folder.
    set "launcher_exit=1"
    goto :finish
)

echo Closing previous ComfyUI instances...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$source = [IO.File]::ReadAllText($env:COMFY_LAUNCHER_FILE); $marker = '# POWERSHELL_CLEANUP'; & ([scriptblock]::Create($source.Substring($source.LastIndexOf($marker) + $marker.Length)))"
set "launcher_exit=%errorlevel%"
if "%launcher_exit%"=="5" goto :elevate
if not "%launcher_exit%"=="0" goto :finish

echo Starting ComfyUI...
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --listen 0.0.0.0 --enable-manager --enable-manager-legacy-ui
set "launcher_exit=%errorlevel%"
if not "%launcher_exit%"=="0" echo ComfyUI exited with an error. Check your Nvidia drivers. For c10.dll errors install https://aka.ms/vc14/vc_redist.x64.exe
goto :finish

:elevate
if defined SSH_CONNECTION goto :finish
if defined SSH_CLIENT goto :finish
if /I "%~1"=="--elevated" goto :finish
echo Administrator permission is needed to close a previous ComfyUI instance.
powershell.exe -NoLogo -NoProfile -Command "try { $command = '/d /s /c ""' + $env:COMFY_LAUNCHER_FILE + '" --elevated"'; Start-Process -FilePath $env:ComSpec -ArgumentList $command -Verb RunAs -ErrorAction Stop; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
set "launcher_exit=%errorlevel%"
popd
exit /b %launcher_exit%

:finish
popd
if not defined SSH_CONNECTION if not defined SSH_CLIENT pause
exit /b %launcher_exit%

# POWERSHELL_CLEANUP
$ErrorActionPreference = 'Stop'
$root = $env:COMFY_PORTABLE_ROOT.TrimEnd('\')
$pythonDirectory = $root + '\python_embeded\'
$port = 8188

function Test-ComfyProcess($process) {
    if ($null -eq $process -or $process.Name -notmatch '^python(w)?\.exe$') { return $false }
    $fromThisFolder = $process.ExecutablePath -and $process.ExecutablePath.StartsWith($pythonDirectory, [StringComparison]::OrdinalIgnoreCase)
    $comfyMain = $process.CommandLine -and $process.CommandLine -match '(?i)ComfyUI[\\/]+main\.py(?:[\s"'']|$)'
    return $fromThisFolder -or $comfyMain
}

function Stop-ComfyProcess($processId) {
    try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
        Write-Host ('Closed ComfyUI process ' + $processId)
    } catch {
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            Write-Host ('Could not close process ' + $processId + ': ' + $_.Exception.Message)
            exit 5
        }
    }
}

try {
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $processes = @(Get-CimInstance Win32_Process | Where-Object { Test-ComfyProcess $_ })
        foreach ($process in $processes) { Stop-ComfyProcess $process.ProcessId }
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($owner in @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
            $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $owner)
            # A launcher using just main.py can still be identified by its listening port.
            $relativeMain = $process -and $process.Name -match '^python(w)?\.exe$' -and $process.CommandLine -match '(?i)(?:^|[\s"''])main\.py(?:[\s"'']|$)'
            if ((Test-ComfyProcess $process) -or $relativeMain) {
                Stop-ComfyProcess $owner
            } elseif ($process -and $process.Name -match '^python(w)?\.exe$' -and -not $process.CommandLine) {
                Write-Host ('Administrator permission is needed to inspect Python process ' + $owner + ' on port ' + $port + '.')
                exit 5
            } elseif ($process) {
                Write-Host ('ERROR: Port ' + $port + ' is used by another application: ' + $process.Name + ' (PID ' + $owner + '). Close it before starting ComfyUI.')
                exit 2
            }
        }
        Start-Sleep -Milliseconds 700
        $remaining = @(Get-CimInstance Win32_Process | Where-Object { Test-ComfyProcess $_ })
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        if ($remaining.Count -eq 0 -and $listeners.Count -eq 0) {
            Write-Host ('Port ' + $port + ' is free.')
            exit 0
        }
    }
    Write-Host ('ERROR: ComfyUI processes or port ' + $port + ' are still active. Startup canceled.')
    exit 2
} catch {
    Write-Host ('ERROR: Could not verify ComfyUI shutdown: ' + $_.Exception.Message)
    exit 1
}
