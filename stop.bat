@echo off
cd /d "%~dp0"
wscript.exe //nologo "%~dp0stop.vbs"
exit /b 0
