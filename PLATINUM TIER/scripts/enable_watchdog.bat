@echo off
REM ============================================================================
REM enable_watchdog.bat - Re-enable Watchdog Auto-Start
REM ============================================================================

net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Run as Administrator!
    pause
    exit /b 1
)

cd /d "%~dp0.."
call scripts\setup_watchdog.bat
