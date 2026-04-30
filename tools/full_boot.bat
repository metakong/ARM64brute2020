@echo off
:: =============================================================================
:: DSIE Codex Full Boot Sequence
:: Triggered by Windows Task Scheduler at logon (30s delay)
:: =============================================================================

:: Phase 0: Force safe temp to prevent VHDX mount race crash
set TEMP=C:\Windows\Temp
set TMP=C:\Windows\Temp

:: Phase 1: Poll for Dev Drive mount
echo [BOOT] Waiting for Dev Drive (Z:) to mount...
:POLL
if not exist "Z:\foundry_project\core\dsie_core.py" (
    timeout /t 2 /nobreak > nul
    goto POLL
)
echo [BOOT] Dev Drive mounted. Proceeding with boot sequence.
cd /d "Z:\foundry_project"

:: Phase 2: Boot the Cognitive Bus (PocketBase)
echo [BOOT] Starting PocketBase on port 8090...
start "" /B "Z:\foundry_project\bus\pocketbase\pocketbase.exe" serve --http="127.0.0.1:8090"
timeout /t 3 /nobreak > nul

:: Phase 3: Boot the NPU Voice Core
echo [BOOT] Starting DSIE Voice Core (NPU)...
start "" "Z:\foundry_project\venv\Scripts\python.exe" "core\dsie_core.py"

:: Phase 4: Serve the Dashboard
echo [BOOT] Starting Dashboard HTTP server on port 8080...
start "" /B "Z:\foundry_project\venv\Scripts\python.exe" -m http.server 8080 --directory "Z:\foundry_project\dashboard"
timeout /t 2 /nobreak > nul

:: Phase 5: Boot the Mercenary Router (Cloud AI Gateway)
echo [BOOT] Starting Mercenary Router on port 8000...
start "" /B "Z:\foundry_project\venv\Scripts\python.exe" "core\mercenary_router.py"
timeout /t 2 /nobreak > nul

:: Phase 6: Open browser to Dashboard
echo [BOOT] Opening Dashboard in browser...
start http://localhost:8080

echo [BOOT] All systems online.
