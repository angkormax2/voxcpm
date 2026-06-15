@echo off
cd /d "%~dp0"
start "" pythonw "%~dp0launcher.py" 2>nul
if errorlevel 1 start "" python "%~dp0launcher.py"
exit /b 0
