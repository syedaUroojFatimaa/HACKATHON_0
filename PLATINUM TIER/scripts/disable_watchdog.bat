@echo off
REM ============================================================================
REM disable_watchdog.bat - Disable Watchdog Auto-Start
REM ============================================================================

echo Disabling watchdog auto-start...
schtasks /Delete /TN "PlatinumTierWatchdog" /F
if %ERRORLEVEL% equ 0 (
    echo [OK] Watchdog task disabled.
) else (
    echo [ERROR] Failed to disable watchdog task.
    echo Task may not exist or requires Administrator privileges.
)
pause
