@echo off
REM Force the working directory to the folder where this .bat file lives
cd /d "%~dp0"

echo [DSIE Codex] Diagnostics...
echo Current Working Directory: %CD%

IF NOT EXIST "Z:\foundry_project\venv\Scripts\python.exe" (
    echo [ERROR] Could not find venv Python at Z:\foundry_project\venv\Scripts\python.exe
    pause
    exit /b
)

IF NOT EXIST "core\dsie_core.py" (
    echo [ERROR] Could not find the core script at %CD%\core\dsie_core.py
    pause
    exit /b
)

echo [DSIE Codex] Venv Python verified.
echo [DSIE Codex] Core script verified.
echo [DSIE Codex] Booting Voice Core via local venv...
echo.

"Z:\foundry_project\venv\Scripts\python.exe" core\dsie_core.py

pause