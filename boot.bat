@echo off
REM Force the working directory to the folder where this .bat file lives
cd /d "%~dp0"

echo [DSIE Codex] Diagnostics...
echo Current Working Directory: %CD%

IF NOT EXIST "C:\Program Files\Python312-arm64\python.exe" (
    echo [ERROR] Could not find native Python at C:\Program Files\Python312-arm64\python.exe
    pause
    exit /b
)

IF NOT EXIST "core\dsie_core.py" (
    echo [ERROR] Could not find the core script at %CD%\core\dsie_core.py
    pause
    exit /b
)

echo [DSIE Codex] Native ARM64 Python verified.
echo [DSIE Codex] Core script verified.
echo [DSIE Codex] Bypassing global PATH and booting Voice Core...
echo.

"C:\Program Files\Python312-arm64\python.exe" core\dsie_core.py

pause