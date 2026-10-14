@echo off
setlocal
cd /d "%~dp0"

set "COMFY_RUNTIME=%~dp0..\.venv\Scripts"
if not exist "%COMFY_RUNTIME%\python.exe" set "COMFY_RUNTIME=%~dp0.venv\Scripts"
if not exist "%COMFY_RUNTIME%\pythonw.exe" goto :repair
"%COMFY_RUNTIME%\python.exe" -I -c "import tkinter, paramiko, PIL, pyte" >nul 2>&1
if errorlevel 1 goto :repair
start "" "%COMFY_RUNTIME%\pythonw.exe" -E -s "%~dp0comfyui_remote_manager.py"
exit /b 0

:repair
echo Run install-client.exe to install or repair ComfyUI Remote Manager.
pause
exit /b 1
