@echo off
title VoxCPM2 Studio By BONG Pisith - Stop Servers

echo.
echo Stopping VoxCPM servers on ports 8000 and 3000...
echo.

set "FOUND=0"

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo   Stopping API on port 8000 ^(PID %%p^)
    taskkill /F /PID %%p >nul 2>&1
    set "FOUND=1"
)

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo   Stopping UI on port 3000 ^(PID %%p^)
    taskkill /F /PID %%p >nul 2>&1
    set "FOUND=1"
)

if "%FOUND%"=="0" (
    echo   No VoxCPM servers were running.
) else (
    echo.
    echo   Done. Servers stopped.
)

echo.
pause
