' Launch VoxCPM2 Studio GUI with no console flash.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
py = dir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then py = "pythonw"
CreateObject("WScript.Shell").Run """" & py & """ """ & dir & "\launcher.py""", 0, False
