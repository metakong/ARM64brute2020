Set WshShell = CreateObject("WScript.Shell")

' 1. The Hardware Wake-Up Delay
' Wait 20 seconds for Qualcomm MCDM drivers to load on Windows boot
WScript.Sleep 20000

' 2. Enforce the Working Directory
WshShell.CurrentDirectory = "Z:\foundry_project"

' 3. Silent Ignition (0 = Hidden Window, /c = Run and terminate CMD wrapper)
WshShell.Run "cmd /c Z:\foundry_project\venv\Scripts\python.exe core\dsie_core.py", 0, False