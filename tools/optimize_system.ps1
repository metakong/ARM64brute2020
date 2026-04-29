
Write-Output "--- SYSTEM OPTIMIZATION INITIATED ---"

# 1. Create Z: Drive Cache Architecture
$zTemp = "Z:\SystemTemp"
$zPip = "Z:\pip_cache"
$zNpm = "Z:\npm_cache"
Write-Output "`n[1] Creating Z: drive cache architecture..."
New-Item -ItemType Directory -Force -Path $zTemp, $zPip, $zNpm | Out-Null
Write-Output "Paths created successfully."

# 2. Reroute Environment Variables (Global Consolidation)
Write-Output "`n[2] Rerouting User Environment Variables..."
[System.Environment]::SetEnvironmentVariable("TEMP", $zTemp, "User")
[System.Environment]::SetEnvironmentVariable("TMP", $zTemp, "User")
[System.Environment]::SetEnvironmentVariable("PIP_CACHE_DIR", $zPip, "User")
[System.Environment]::SetEnvironmentVariable("npm_config_cache", $zNpm, "User")
Write-Output "User variables mapped to Z: drive."

Write-Output "`n[3] Rerouting System (Machine) Environment Variables..."
try {
    [System.Environment]::SetEnvironmentVariable("TEMP", $zTemp, "Machine")
    [System.Environment]::SetEnvironmentVariable("TMP", $zTemp, "Machine")
    Write-Output "System variables successfully updated to Z: drive (Admin privileges confirmed)."
} catch {
    Write-Output "[!] FATAL ERROR: Could not set System variables. This script MUST be executed as Administrator."
}

# 3. Purge C: Drive Residue
Write-Output "`n[4] Purging legacy C: drive caches..."
$bytesFreed = 0

$purgePaths = @(
    "$env:LOCALAPPDATA\Temp\*",
    "$env:LOCALAPPDATA\pip\cache\*",
    "$env:LOCALAPPDATA\npm-cache\*"
)

foreach ($path in $purgePaths) {
    # Suppress errors for files currently in use by the OS
    Remove-Item -Path $path -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output "Legacy caches flushed from C: drive."
Write-Output "`n--- OPTIMIZATION COMPLETE ---"
Write-Output "NOTE: The user will need to restart their terminal/IDE for the new Environment Variables to take effect."
