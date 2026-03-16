@echo off
REM ============================================================================
REM health_monitor.bat - System Health Check Script
REM ============================================================================
REM Quick health check that can be run manually or scheduled
REM ============================================================================

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%.."

echo.
echo ============================================================================
echo   System Health Monitor
echo   %DATE% %TIME%
echo ============================================================================
echo.

REM Check if Python is available
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in PATH
    goto :error
)

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Run watchdog health check
echo [INFO] Running health check...
echo.
python watchdog.py --check

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Health check failed
    goto :error
)

echo.
echo [OK] Health check completed
echo.

REM Show quick status summary
echo ============================================================================
echo   Quick Status Summary
echo ============================================================================
echo.

REM Check PM2 status if available
where pm2 >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo PM2 Process Status:
    pm2 status --no-color
    echo.
)

REM Show recent health log
if exist "Logs\system_health.md" (
    echo Recent Health Log (last 20 lines):
    echo.
    powershell -Command "Get-Content 'Logs\system_health.md' -Tail 20"
)

echo.
echo ============================================================================
echo   Full Report: Logs\system_health.md
echo   Watchdog Log: Logs\watchdog.log
echo ============================================================================
echo.

exit /b 0

:error
exit /b 1
