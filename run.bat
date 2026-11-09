@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0" || goto :repair

set "COMFY_RUNTIME=%~dp0.venv\Scripts"
if not exist "%~dp0app\comfyui_remote_manager.py" goto :repair
if not exist "%COMFY_RUNTIME%\pythonw.exe" goto :repair
"%COMFY_RUNTIME%\python.exe" -I -c "import tkinter, paramiko, PIL, pyte" >nul 2>&1
if errorlevel 1 goto :repair
start "" "%COMFY_RUNTIME%\pythonw.exe" -E -s -m app.comfyui_remote_manager
exit /b 0

:repair
if exist "%~dp0install-client.bat" (
    echo Run install-client.bat to prepare ComfyUI Remote Manager.
) else (
    echo Run the PC Client installer to repair ComfyUI Remote Manager.
)
pause
exit /b 1
