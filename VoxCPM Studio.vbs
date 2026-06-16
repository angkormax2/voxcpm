' Launch VoxCPM Studio GUI with resilient Python fallback.
Option Explicit

Dim fso, sh, dirPath, launcherPath, pyExe, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

dirPath = fso.GetParentFolderName(WScript.ScriptFullName)
launcherPath = dirPath & "\launcher.py"

If Not fso.FileExists(launcherPath) Then
  MsgBox "launcher.py was not found." & vbCrLf & launcherPath, vbCritical, "SINEKOOL AI"
  WScript.Quit 1
End If

pyExe = ""
If fso.FileExists(dirPath & "\.venv\Scripts\pythonw.exe") Then
  pyExe = """" & dirPath & "\.venv\Scripts\pythonw.exe" & """"
ElseIf fso.FileExists(dirPath & "\.venv\Scripts\python.exe") Then
  pyExe = """" & dirPath & "\.venv\Scripts\python.exe" & """"
ElseIf CommandExists("pyw") Then
  pyExe = "pyw -3"
ElseIf CommandExists("py") Then
  pyExe = "py -3"
ElseIf CommandExists("pythonw") Then
  pyExe = "pythonw"
ElseIf CommandExists("python") Then
  pyExe = "python"
End If

If pyExe = "" Then
  MsgBox "Python was not found." & vbCrLf & _
         "Please install Python or run from a prepared package.", vbCritical, "SINEKOOL AI"
  WScript.Quit 2
End If

cmd = pyExe & " """ & launcherPath & """"
sh.Run cmd, 0, False

Function CommandExists(cmdName)
  On Error Resume Next
  Dim execObj
  Set execObj = sh.Exec("cmd /c where " & cmdName)
  If Err.Number <> 0 Then
    CommandExists = False
    Err.Clear
    Exit Function
  End If
  Do While execObj.Status = 0
    WScript.Sleep 20
  Loop
  CommandExists = (execObj.ExitCode = 0)
  On Error Goto 0
End Function
