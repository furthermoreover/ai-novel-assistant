@echo off
chcp 65001 >nul
title Register PostgreSQL Service
echo ============================================
echo   Register PostgreSQL as Windows Service
echo   (Run this as Administrator, once)
echo ============================================
echo.

REM Stop current manual instance first (avoid conflict)
echo [1/4] Stopping current PostgreSQL instance...
"D:\SQL\bin\pg_ctl.exe" -D "D:\SQL\data" stop -m fast >nul 2>&1
timeout /t 3 /nobreak >nul

REM Register service with auto start
echo [2/4] Registering service...
"D:\SQL\bin\pg_ctl.exe" register -N "PostgreSQL" -D "D:\SQL\data" -S auto
if errorlevel 1 (
    echo [ERROR] Failed to register service.
    echo        Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)

REM Start the service now
echo [3/4] Starting service...
net start PostgreSQL >nul 2>&1
if errorlevel 1 (
    echo [WARN] Service registered but start failed, will start on next boot.
) else (
    echo   Service started OK.
)

echo [4/4] Done!
echo.
echo   PostgreSQL is now a Windows service with AUTO start.
echo   It will run in background after every boot - no manual start needed.
echo.
echo   Next: just double-click start.bat to launch the novel assistant.
echo.
pause
