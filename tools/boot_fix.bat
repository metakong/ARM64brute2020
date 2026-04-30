@echo off
:: Force local temp to C: to prevent CMD crash if Z: is unmounted
set TEMP=C:\Windows\Temp
set TMP=C:\Windows\Temp
:POLL
if not exist "Z:\foundry_project\core\dsie_core.py" (
    timeout /t 2 /nobreak > nul
    goto POLL
)
cd /d "Z:\foundry_project"
start "" "Z:\foundry_project\venv\Scripts\python.exe" "core\dsie_core.py"
