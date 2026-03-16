@echo off
REM ============================================================================
REM pm2_startup.bat - PM2 Auto-Start Helper for Windows Task Scheduler
REM ============================================================================
REM This script is called by Windows Task Scheduler at system startup.
REM It waits for the system to be ready, then starts all PM2 processes.
REM ============================================================================

REM Change to the vault directory
cd /d "%~dp0.."

REM Wait for network and system to stabilize (30 seconds)
timeout /t 30 /nobreak >nul

REM Check if PM2 is available
where pm2 >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [%DATE% %TIME%] ERROR: PM2 not found in PATH >> Logs\startup.log
    exit /b 1
)

REM Start PM2 processes
echo [%DATE% %TIME%] Starting PM2 processes... >> Logs\startup.log
pm2 start ecosystem.config.js >> Logs\startup.log 2>&1

if %ERRORLEVEL% neq 0 (
    echo [%DATE% %TIME%] ERROR: Failed to start PM2 >> Logs\startup.log
    exit /b 1
)

REM Save PM2 process list
pm2 save >> Logs\startup.log 2>&1

echo [%DATE% %TIME%] PM2 processes started successfully >> Logs\startup.log
exit /b 0
