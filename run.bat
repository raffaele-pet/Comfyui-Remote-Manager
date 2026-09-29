@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0..\.venv\Scripts\pythonw.exe" (
    start "" "%~dp0..\.venv\Scripts\pythonw.exe" "%~dp0comfyui_remote_manager.py"
    exit /b 0
)

where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pyw.exe -3 "%~dp0comfyui_remote_manager.py"
    exit /b 0
)

where py.exe >nul 2>nul
if errorlevel 1 (
    echo Python non trovato. Installa Python 3 e riprova.
    pause
    exit /b 1
)

py.exe -3 "%~dp0comfyui_remote_manager.py"
if errorlevel 1 pause
