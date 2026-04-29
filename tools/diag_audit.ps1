
$paths = @(
    "$env:USERPROFILE\.foundry",
    "$env:USERPROFILE\.cache",
    "$env:LOCALAPPDATA\Temp",
    "$env:LOCALAPPDATA\pip\cache",
    "$env:LOCALAPPDATA\npm-cache"
)

Write-Output "--- 1. C: DRIVE RESIDUE AUDIT ---"
foreach ($path in $paths) {
    if (Test-Path $path) {
        $items = Get-ChildItem $path -Recurse -ErrorAction SilentlyContinue
        if ($items) {
            $size = ($items | Measure-Object -Property Length -Sum).Sum
            $sizeMB = [Math]::Round($size / 1MB, 2)
            $sizeGB = [Math]::Round($size / 1GB, 4)
            Write-Output "$path : $sizeMB MB ($sizeGB GB)"
        } else {
            Write-Output "$path : 0 MB (Exists but Empty)"
        }
    } else {
        Write-Output "$path : Not Found"
    }
}

Write-Output "`n--- 2. ENVIRONMENT VARIABLES ---"
Write-Output "[USER]"
$userVars = [System.Environment]::GetEnvironmentVariables('User')
$userVars.GetEnumerator() | Where-Object { $_.Key -match 'TEMP|TMP|PATH|FOUNDRY' } | Select-Object Key, Value | Format-Table -AutoSize | Out-String | Write-Output

Write-Output "[SYSTEM]"
$sysVars = [System.Environment]::GetEnvironmentVariables('Machine')
$sysVars.GetEnumerator() | Where-Object { $_.Key -match 'TEMP|TMP|PATH|FOUNDRY' } | Select-Object Key, Value | Format-Table -AutoSize | Out-String | Write-Output

Write-Output "`n--- 3. SECURITY & I/O AUDIT ---"
Write-Output "[Defender Exclusions]"
$exclusions = Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
if ($exclusions) {
    $exclusions | Write-Output
} else {
    Write-Output "No Defender exclusions found."
}

Write-Output "`n[Windows Search Indexing]"
# Checking if Z: is indexed (basic check via registry)
$searchReg = "HKLM:\SOFTWARE\Microsoft\Windows Search\CrawlScopeManager\Windows\SystemIndex\WorkingSetRules"
if (Test-Path $searchReg) {
    Get-ChildItem $searchReg | ForEach-Object { Get-ItemProperty $_.PsPath } | Select-Object URL | Write-Output
} else {
    Write-Output "Could not access Search Indexer registry path."
}

Write-Output "`n--- 4. STARTUP & BLOAT ---"
Write-Output "[Startup Applications]"
Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location | Format-Table -AutoSize | Out-String | Write-Output

Write-Output "`n[High resource Background Processes]"
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name, CPU, WorkingSet | Format-Table -AutoSize | Out-String | Write-Output
