@echo off
REM ============================================================================
REM health_check.bat - Platinum Tier AI Employee Health Check
REM ============================================================================
REM Performs comprehensive health checks on all running processes and system
REM ============================================================================

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================================================
echo   Platinum Tier AI Employee - Health Check
echo   %DATE% %TIME%
echo ============================================================================
echo.

set "ERROR_COUNT=0"
set "WARNING_COUNT=0"

REM ============================================================================
REM 1. Check PM2 Daemon Status
REM ============================================================================
echo [1/8] Checking PM2 daemon status...
pm2 list >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] PM2 daemon is not running!
    set /a ERROR_COUNT+=1
) else (
    echo   [OK] PM2 daemon is running.
)
echo.

REM ============================================================================
REM 2. Check Process Status
REM ============================================================================
echo [2/8] Checking process status...
echo.

set "ONLINE_COUNT=0"
set "STOPPED_COUNT=0"
set "ERRORED_COUNT=0"

for /f "tokens=*" %%i in ('pm2 list --no-color 2^>nul') do (
    echo %%i | findstr "online" >nul 2>nul
    if not errorlevel 1 (
        set /a ONLINE_COUNT+=1
    )
    echo %%i | findstr "stopped" >nul 2>nul
    if not errorlevel 1 (
        set /a STOPPED_COUNT+=1
    )
    echo %%i | findstr "errored" >nul 2>nul
    if not errorlevel 1 (
        set /a ERRORED_COUNT+=1
    )
)

echo   Online processes:  !ONLINE_COUNT!
echo   Stopped processes: !STOPPED_COUNT!
echo   Errored processes: !ERRORED_COUNT!
echo.

if !ERRORED_COUNT! gtr 0 (
    echo   [ERROR] Some processes are in errored state!
    set /a ERROR_COUNT+=1
)
if !STOPPED_COUNT! gtr 0 (
    echo   [WARNING] Some processes are stopped.
    set /a WARNING_COUNT+=1
)
if !ONLINE_COUNT! equ 0 (
    echo   [ERROR] No processes are online!
    set /a ERROR_COUNT+=1
) else (
    echo   [OK] Processes are running.
)
echo.

REM ============================================================================
REM 3. Check Python Environment
REM ============================================================================
echo [3/8] Checking Python environment...
if exist "venv\Scripts\python.exe" (
    echo   [OK] Virtual environment exists.
    for /f "tokens=*" %%v in ('venv\Scripts\python.exe --version 2^>^&1') do echo   Version: %%v
) else (
    echo   [ERROR] Virtual environment not found!
    set /a ERROR_COUNT+=1
)
echo.

REM ============================================================================
REM 4. Check Required Directories
REM ============================================================================
echo [4/8] Checking required directories...
set "DIR_ERROR=0"
for %%d in (Inbox Needs_Action Needs_Approval Done Logs Plans Reports) do (
    if exist "%%d" (
        echo   [OK] %%d\
    ) else (
        echo   [ERROR] %%d\ - Missing!
        set /a DIR_ERROR+=1
    )
)
if !DIR_ERROR! gtr 0 set /a ERROR_COUNT+=1
echo.

REM ============================================================================
REM 5. Check Log Files
REM ============================================================================
echo [5/8] Checking log files...

REM Check main application logs
if exist "Logs\ai_employee.log" (
    for %%F in ("Logs\ai_employee.log") do set "LOG_SIZE=%%~zF"
    set /a LOG_MB=!LOG_SIZE!/1048576
    echo   [OK] ai_employee.log (!LOG_MB! MB)
) else (
    echo   [INFO] ai_employee.log - Not yet created
)

if exist "Logs\watcher_errors.log" (
    for %%F in ("Logs\watcher_errors.log") do set "LOG_SIZE=%%~zF"
    set /a LOG_MB=!LOG_SIZE!/1048576
    echo   [OK] watcher_errors.log (!LOG_MB! MB)
) else (
    echo   [OK] watcher_errors.log - No errors recorded
)

REM Check for recent errors in log
if exist "Logs\watcher_errors.log" (
    for /f "tokens=*" %%i in ('find /c /v "" "Logs\watcher_errors.log" 2^>nul') do (
        set "ERROR_LINES=%%i"
    )
    if !ERROR_LINES! gtr 1 (
        echo   [WARNING] watcher_errors.log has !ERROR_LINES! lines
        set /a WARNING_COUNT+=1
    )
)
echo.

REM ============================================================================
REM 6. Check Lock Files
REM ============================================================================
echo [6/8] Checking lock files...
if exist "Logs\.scheduler.lock" (
    set /p SCHEDULER_PID=<"Logs\.scheduler.lock"
    REM Check if process is still alive
    tasklist /FI "PID eq !SCHEDULER_PID!" 2>nul | findstr "!SCHEDULER_PID!" >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] Scheduler lock present (PID !SCHEDULER_PID!)
    ) else (
        echo   [WARNING] Stale lock file found (PID !SCHEDULER_PID! not running)
        set /a WARNING_COUNT+=1
    )
) else (
    echo   [INFO] No scheduler lock (scheduler may not be running)
)
echo.

REM ============================================================================
REM 7. Check Disk Space
REM ============================================================================
echo [7/8] Checking disk space...
for /f "tokens=3" %%d in ('wmic logicaldisk where "DeviceID='%~d0'" get FreeSpace ^| findstr [0-9]') do set "FREE_SPACE=%%d"
set /a FREE_GB=!FREE_SPACE!/1073741824
if !FREE_GB! lss 1 (
    echo   [WARNING] Low disk space: !FREE_GB! GB free
    set /a WARNING_COUNT+=1
) else (
    echo   [OK] Disk space: !FREE_GB! GB free
)
echo.

REM ============================================================================
REM 8. Quick Process Response Test
REM ============================================================================
echo [8/8] Testing AI Employee status command...
call venv\Scripts\activate.bat 2>nul
python scripts\run_ai_employee.py --status >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   [OK] AI Employee responded to status check.
) else (
    echo   [WARNING] AI Employee status check failed.
    set /a WARNING_COUNT+=1
)
echo.

REM ============================================================================
REM Summary
REM ============================================================================
echo ============================================================================
echo   Health Check Summary
echo ============================================================================
echo.
echo   Errors:   !ERROR_COUNT!
echo   Warnings: !WARNING_COUNT!
echo.

if !ERROR_COUNT! gtr 0 (
    echo   [ACTION REQUIRED] Please address the errors above.
    echo.
    echo   Suggested fixes:
    echo   - Run: start.bat to restart all processes
    echo   - Check: Logs\ folder for error details
    echo   - Verify: Python and Node.js are installed
) else if !WARNING_COUNT! gtr 0 (
    echo   [OK] System is running with minor warnings.
) else (
    echo   [HEALTHY] All systems operational.
)
echo.
echo ============================================================================
echo.

REM Exit with error code if errors found
if !ERROR_COUNT! gtr 0 exit /b 1
exit /b 0
