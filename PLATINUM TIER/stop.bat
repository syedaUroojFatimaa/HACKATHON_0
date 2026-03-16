@echo off
REM ============================================================================
REM stop.bat - Platinum Tier AI Employee Shutdown Script
REM ============================================================================
REM Gracefully stops all PM2 processes
REM ============================================================================

setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================================================
echo   Platinum Tier AI Employee - Shutdown Script
echo ============================================================================
echo.

REM Check if PM2 is available
where pm2 >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] PM2 is not installed or not in PATH.
    pause
    exit /b 1
)

echo [INFO] Stopping all PM2 processes...
pm2 stop ecosystem.config.js

echo.
echo [OK] All processes stopped.
echo.
echo Note: Processes are stopped but not deleted.
echo       Use 'start.bat' to restart them.
echo.

endlocal
exit /b 0
