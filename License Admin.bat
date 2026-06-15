@echo off
cd /d "%~dp0"
start "" pythonw "%~dp0license_admin.py" 2>nul
if errorlevel 1 start "" python "%~dp0license_admin.py"
exit /b 0
