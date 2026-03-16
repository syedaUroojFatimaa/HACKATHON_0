@echo off
REM ============================================================================
REM start.bat - Platinum Tier AI Employee Startup Script
REM ============================================================================
REM This script starts all PM2 processes for 24/7 operation.
REM Run from: C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER
REM ============================================================================

setlocal EnableDelayedExpansion

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================================================
echo   Platinum Tier AI Employee - Startup Script
echo ============================================================================
echo.

REM Check if Python is available
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://python.org/downloads
    pause
    exit /b 1
)

echo [OK] Python found: 
python --version
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Creating one...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment found.
)
echo.

REM Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated.
echo.

REM Check if dependencies are installed
echo [INFO] Checking dependencies...
python -c "import tweepy" 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing Python dependencies...
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] Some dependencies may have failed to install.
    )
) else (
    echo [OK] Dependencies installed.
)
echo.

REM Check if Node.js and PM2 are available
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)

where pm2 >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] PM2 is not installed. Installing...
    npm install -g pm2
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install PM2.
        pause
        exit /b 1
    )
)

echo [OK] PM2 found:
pm2 --version
echo.

REM Create required directories if they don't exist
echo [INFO] Ensuring required directories exist...
for %%d in (Inbox Needs_Action Needs_Approval Done Logs Plans Reports Accounting Errors) do (
    if not exist "%%d" (
        mkdir "%%d"
        echo   Created: %%d
    )
)
echo [OK] Directories ready.
echo.

REM Check if PM2 processes are already running
echo [INFO] Checking PM2 status...
pm2 status --no-color | findstr "online" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [WARNING] Some PM2 processes are already running.
    echo.
    choice /C YN /M "Do you want to restart all processes"
    if errorlevel 2 (
        echo [INFO] Keeping existing processes running.
        echo.
        echo Current PM2 status:
        pm2 status
        echo.
        goto :show_logs_option
    )
    echo [INFO] Stopping existing processes...
    pm2 stop all
    pm2 delete all
)
echo.

REM Start all PM2 processes
echo ============================================================================
echo   Starting PM2 Processes
echo ============================================================================
echo.

echo [INFO] Starting orchestrator, file-watcher, and log-manager...
pm2 start ecosystem.config.js

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to start PM2 processes.
    echo Check Logs\ for error details.
    pause
    exit /b 1
)

echo.
echo [OK] All processes started successfully!
echo.

REM Save PM2 process list for auto-resume on system restart
echo [INFO] Saving PM2 process list...
pm2 save
echo [OK] PM2 process list saved.
echo.

REM Show process status
echo ============================================================================
echo   Process Status
echo ============================================================================
echo.
pm2 status
echo.

:show_logs_option
echo ============================================================================
echo   Quick Commands
echo ============================================================================
echo.
echo   View logs:           pm2 logs
echo   View status:         pm2 status
echo   Stop all:            pm2 stop all
echo   Restart all:         pm2 restart all
echo   Health check:        scripts\health_check.bat
echo   AI Employee status:  venv\Scripts\activate ^&^& python scripts\run_ai_employee.py --status
echo.
echo ============================================================================
echo   The AI Employee is now running 24/7!
echo ============================================================================
echo.

REM Optional: Show logs for a few seconds
choice /C YN /M "Do you want to view live logs (press N to exit)"
if errorlevel 2 (
    goto :end
)

echo.
echo [INFO] Showing live logs. Press Ctrl+C to stop viewing.
echo.
pm2 logs --lines 50

:end
echo.
echo [INFO] Startup script completed.
endlocal
exit /b 0
