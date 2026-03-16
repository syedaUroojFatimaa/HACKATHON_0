@echo off
REM ============================================================================
REM setup_watchdog.bat - Windows Task Scheduler Setup for Watchdog
REM ============================================================================
REM Configures Windows Task Scheduler to run watchdog.py every 5 minutes
REM
REM IMPORTANT: Run this script as Administrator!
REM ============================================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================================================
echo   System Watchdog - Task Scheduler Configuration
echo ============================================================================
echo.

REM Check for administrator privileges
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] This script must be run as Administrator!
    echo.
    echo Please right-click and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo [OK] Running with administrator privileges.
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
set "VAULT_DIR=%SCRIPT_DIR:~0,-1%"

echo [INFO] Vault directory: %VAULT_DIR%
echo.

REM ============================================================================
REM Configuration
REM ============================================================================
set "TASK_NAME=PlatinumTierWatchdog"
set "CHECK_INTERVAL=5"

echo [INFO] Configuration:
echo   Task Name: %TASK_NAME%
echo   Check Interval: Every %CHECK_INTERVAL% minutes
echo.

REM ============================================================================
REM Step 1: Check prerequisites
REM ============================================================================
echo [1/5] Checking prerequisites...

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

where schtasks >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] schtasks command not found.
    pause
    exit /b 1
)
echo [OK] Task Scheduler available.
echo.

REM ============================================================================
REM Step 2: Create the watchdog runner script
REM ============================================================================
echo [2/5] Creating watchdog runner script...

set "RUNNER_SCRIPT=%VAULT_DIR%\scripts\run_watchdog.bat"

echo Creating: %RUNNER_SCRIPT%
(
    echo @echo off
    echo REM ============================================================================
    echo REM run_watchdog.bat - Called by Task Scheduler
    echo REM ============================================================================
    echo.
    echo setlocal
    echo.
    echo cd /d "%VAULT_DIR%"
    echo.
    echo REM Activate virtual environment if it exists
    echo if exist "venv\Scripts\activate.bat" (
    echo     call venv\Scripts\activate.bat
    echo )
    echo.
    echo REM Run health check
    echo python watchdog.py --check
    echo.
    echo exit /b 0
) > "!RUNNER_SCRIPT!"

echo [OK] Runner script created.
echo.

REM ============================================================================
REM Step 3: Delete existing task if present
REM ============================================================================
echo [3/5] Removing existing task (if any)...
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>nul
echo [OK] Previous task removed (if existed).
echo.

REM ============================================================================
REM Step 4: Create the scheduled task
REM ============================================================================
echo [4/5] Creating scheduled task...
echo.

REM Create task that runs every 5 minutes
schtasks /Create /TN "%TASK_NAME%" ^
    /TR "\"%RUNNER_SCRIPT%\"" ^
    /SC MINUTE ^
    /MO %CHECK_INTERVAL% ^
    /RU SYSTEM ^
    /RL HIGHEST ^
    /F

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to create scheduled task.
    pause
    exit /b 1
)

echo [OK] Scheduled task created successfully.
echo.

REM ============================================================================
REM Step 5: Verify the task
REM ============================================================================
echo [5/5] Verifying scheduled task...
echo.
schtasks /Query /TN "%TASK_NAME%"
echo.

REM ============================================================================
REM Create helper scripts
REM ============================================================================
echo Creating helper scripts...
echo.

REM Disable auto-start task
set "DISABLE_SCRIPT=%VAULT_DIR%\scripts\disable_watchdog.bat"
echo Creating: %DISABLE_SCRIPT%
(
    echo @echo off
    echo echo Disabling watchdog auto-start...
    echo schtasks /Delete /TN "%TASK_NAME%" /F
    echo if %ERRORLEVEL% equ 0 (
    echo     echo [OK] Watchdog task disabled.
    echo ) else (
    echo     echo [ERROR] Failed to disable watchdog task.
    echo )
    echo pause
) > "!DISABLE_SCRIPT!"

REM Enable auto-start task (re-create)
set "ENABLE_SCRIPT=%VAULT_DIR%\scripts\enable_watchdog.bat"
echo Creating: %ENABLE_SCRIPT%
(
    echo @echo off
    echo echo Re-enabling watchdog auto-start...
    echo net session ^>nul 2^>^&1
    echo if %ERRORLEVEL% neq 0 (
    echo     echo [ERROR] Run as Administrator!
    echo     pause
    echo     exit /b 1
    echo )
    echo cd /d "%VAULT_DIR%"
    echo call scripts\setup_watchdog.bat
) > "!ENABLE_SCRIPT!"

echo [OK] Helper scripts created.
echo.

REM ============================================================================
REM Summary
REM ============================================================================
echo ============================================================================
echo   Configuration Complete!
echo ============================================================================
echo.
echo Task Details:
echo   Name: %TASK_NAME%
echo   Trigger: Every %CHECK_INTERVAL% minutes
echo   Run As: SYSTEM (Highest privileges)
echo   Script: %RUNNER_SCRIPT%
echo.
echo To verify the task is working:
echo   1. Wait %CHECK_INTERVAL% minutes for first run
echo   2. Check Logs\system_health.md
echo   3. Run: schtasks /Query /TN "%TASK_NAME%"
echo.
echo To view or modify the task:
echo   1. Open Task Scheduler (taskschd.msc)
echo   2. Find "%TASK_NAME%" in the task list
echo.
echo To run watchdog manually:
echo   python watchdog.py --check
echo   python watchdog.py --status
echo.
echo To disable auto-start:
echo   scripts\disable_watchdog.bat
echo.
echo To re-enable auto-start:
echo   scripts\enable_watchdog.bat ^(as Administrator^)
echo.
echo ============================================================================
echo.

pause
exit /b 0
