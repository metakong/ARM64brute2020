
Write-Output "--- WINDOWS 11 TWEAK & DEBLOAT AUDIT ---"

# 1. Defender & Security Services
Write-Output "`n[Windows Defender (WinDefend)]"
Get-Service WinDefend -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String | Write-Output
$defReg = Get-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender" -ErrorAction SilentlyContinue
if ($defReg) { Write-Output "Registry Policies: DisableAntiSpyware = $($defReg.DisableAntiSpyware)" } else { Write-Output "No Policy Override Found" }

# 2. Telemetry & Data Collection (DiagTrack)
Write-Output "`n[Telemetry Service (DiagTrack)]"
Get-Service DiagTrack -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String | Write-Output
$telReg = Get-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" -ErrorAction SilentlyContinue
if ($telReg) { Write-Output "Registry Policies: AllowTelemetry = $($telReg.AllowTelemetry)" } else { Write-Output "No Policy Override Found" }

# 3. Windows Search Indexer
Write-Output "`n[Windows Search Indexer (WSearch)]"
Get-Service WSearch -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String | Write-Output

# 4. Windows Update & Background Transfer
Write-Output "`n[Windows Update (wuauserv)]"
Get-Service wuauserv -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String | Write-Output
Write-Output "`n[Background Intelligent Transfer Service (BITS)]"
Get-Service BITS -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String | Write-Output

# 5. Core Isolation / VBS (Virtualization Based Security)
Write-Output "`n[Virtualization Based Security (VBS) Status]"
$vbs = Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard -ErrorAction SilentlyContinue
if ($vbs) { 
    Write-Output "Status Code: $($vbs.VirtualizationBasedSecurityStatus) (0=Disabled, 1=Enabled without lock, 2=Enabled with lock)" 
} else { 
    Write-Output "VBS State Unknown" 
}

# 6. Power Plan Configuration
Write-Output "`n[Active Power Plan]"
Get-CimInstance -ClassName Win32_PowerPlan -Namespace root\cimv2\power | Where-Object IsActive -eq $true | Select-Object ElementName | Format-Table -AutoSize | Out-String | Write-Output
