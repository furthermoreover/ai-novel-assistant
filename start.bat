@echo off
title AI Novel Assistant - Python
cd /d "%~dp0"

echo ============================================
echo   AI Novel Assistant (Python + FastAPI)
echo ============================================
echo.

REM 如果服务已在运行，直接打开浏览器，避免端口占用报错
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo [提示] 服务已在运行，正在打开浏览器...
    start http://127.0.0.1:8000
    timeout /t 2 /nobreak >nul
    exit /b 0
)

REM Check Python venv
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Please install Python 3.10+ first.
        pause
        exit /b 1
    )
)

echo [1/3] Installing dependencies...
".venv\Scripts\pip.exe" install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

REM 提示：请将下面两处 YOUR_PASSWORD 替换为你的 PostgreSQL 密码
REM Check PostgreSQL reachable, auto-start if not running
echo [2/3] Checking PostgreSQL connection...
".venv\Scripts\python.exe" -c "import psycopg; c=psycopg.connect('postgresql://postgres:YOUR_PASSWORD@localhost:29934/novel_assistant'); c.close(); print('  -> PostgreSQL OK')" 2>nul
if errorlevel 1 (
    echo   -> PostgreSQL not running, trying to start it...
    if exist "D:\SQL\bin\pg_ctl.exe" (
        "D:\SQL\bin\pg_ctl.exe" -D "D:\SQL\data" -l "D:\SQL\data\pg.log" start >nul 2>&1
        timeout /t 5 /nobreak >nul
        ".venv\Scripts\python.exe" -c "import psycopg; c=psycopg.connect('postgresql://postgres:YOUR_PASSWORD@localhost:29934/novel_assistant'); c.close(); print('  -> PostgreSQL started OK')" 2>nul
        if errorlevel 1 (
            echo [ERROR] PostgreSQL started but still unreachable on port 29934.
            echo        Check manually:  D:\SQL\bin\pg_ctl.exe -D D:\SQL\data start
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] PostgreSQL not found at D:\SQL. Please install or adjust path.
        pause
        exit /b 1
    )
)

REM Start server
echo [3/3] Starting server at http://127.0.0.1:8000 ...
echo.
echo   Open your browser:  http://127.0.0.1:8000
echo   Press Ctrl+C to stop.
echo.
cd /d "%~dp0backend"
"..\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000

pause
