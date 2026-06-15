' Stop VoxCPM servers with no console window.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
py = dir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then py = "pythonw"
CreateObject("WScript.Shell").Run """" & py & """ """ & dir & "\stop_servers.py""", 0, False
