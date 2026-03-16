@echo off
REM ============================================================================
REM setup_ceo_briefing.bat - Windows Task Scheduler Setup for CEO Briefing
REM ============================================================================
REM Configures Windows Task Scheduler to generate CEO briefing every Sunday
REM at 8:00 AM
REM
REM IMPORTANT: Run this script as Administrator!
REM ============================================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================================================
echo   CEO Weekly Briefing - Task Scheduler Configuration
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
set "TASK_NAME=PlatinumTierCEOBriefing"
set "SCHEDULE_DAY=SUNDAY"
set "SCHEDULE_TIME=08:00"

echo [INFO] Configuration:
echo   Task Name: %TASK_NAME%
echo   Schedule: Every %SCHEDULE_DAY% at %SCHEDULE_TIME%
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
REM Step 2: Create the briefing runner script
REM ============================================================================
echo [2/5] Creating briefing runner script...

set "RUNNER_SCRIPT=%VAULT_DIR%\scripts\run_ceo_briefing.bat"

echo Creating: %RUNNER_SCRIPT%
(
    echo @echo off
    echo REM ============================================================================
    echo REM run_ceo_briefing.bat - Called by Task Scheduler every Sunday
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
    echo REM Generate weekly briefing
    echo python ceo_briefing.py --generate
    echo.
    echo REM Log completion
    echo for /f "tokens=2 delims==" %%%%i in ^('wmic os get localdatetime /value^') do set "dt=%%%%i"
    echo set "TIMESTAMP=!dt:~0,4!-!dt:~4,2!-!dt:~6,2! !dt:~8,2!:!dt:~10,2!:!dt:~12,2!"
    echo [!TIMESTAMP!] CEO Briefing generated ^>^> Logs\ceo_briefing.log
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

REM Create task that runs every Sunday at 8:00 AM
schtasks /Create /TN "%TASK_NAME%" ^
    /TR "\"%RUNNER_SCRIPT%\"" ^
    /SC WEEKLY ^
    /D %SCHEDULE_DAY% ^
    /ST %SCHEDULE_TIME% ^
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

REM Disable task
set "DISABLE_SCRIPT=%VAULT_DIR%\scripts\disable_ceo_briefing.bat"
echo Creating: %DISABLE_SCRIPT%
(
    echo @echo off
    echo echo Disabling CEO briefing auto-generation...
    echo schtasks /Delete /TN "%TASK_NAME%" /F
    echo if %ERRORLEVEL% equ 0 (
    echo     echo [OK] CEO briefing task disabled.
    echo ) else (
    echo     echo [ERROR] Failed to disable task.
    echo )
    echo pause
) > "!DISABLE_SCRIPT!"

REM Enable task
set "ENABLE_SCRIPT=%VAULT_DIR%\scripts\enable_ceo_briefing.bat"
echo Creating: %ENABLE_SCRIPT%
(
    echo @echo off
    echo echo Re-enabling CEO briefing auto-generation...
    echo net session ^>nul 2^>^&1
    echo if %ERRORLEVEL% neq 0 (
    echo     echo [ERROR] Run as Administrator!
    echo     pause
    echo     exit /b 1
    echo )
    echo cd /d "%VAULT_DIR%"
    echo call scripts\setup_ceo_briefing.bat
) > "!ENABLE_SCRIPT!"

REM Run now (manual trigger)
set "RUN_NOW_SCRIPT=%VAULT_DIR%\scripts\run_ceo_briefing_now.bat"
echo Creating: %RUN_NOW_SCRIPT%
(
    echo @echo off
    echo echo Running CEO briefing generation now...
    echo cd /d "%VAULT_DIR%"
    echo.
    echo if exist "venv\Scripts\activate.bat" (
    echo     call venv\Scripts\activate.bat
    echo )
    echo.
    echo python ceo_briefing.py --generate
    echo.
    echo pause
) > "!RUN_NOW_SCRIPT!"

echo [OK] Helper scripts created.
echo.

REM ============================================================================
REM Create Briefings folder
REM ============================================================================
echo Creating Briefings folder...
if not exist "%VAULT_DIR%\Briefings" mkdir "%VAULT_DIR%\Briefings"
echo [OK] Briefings folder created.
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
echo   Trigger: Every %SCHEDULE_DAY% at %SCHEDULE_TIME%
echo   Run As: SYSTEM (Highest privileges)
echo   Script: %RUNNER_SCRIPT%
echo.
echo To test the briefing generation:
echo   python ceo_briefing.py --generate
echo   or run: scripts\run_ceo_briefing_now.bat
echo.
echo To view or modify the task:
echo   1. Open Task Scheduler (taskschd.msc)
echo   2. Find "%TASK_NAME%" in the task list
echo.
echo To run manually (for testing):
echo   schtasks /Run /TN "%TASK_NAME%"
echo.
echo To disable auto-generation:
echo   scripts\disable_ceo_briefing.bat
echo.
echo To re-enable auto-generation:
echo   scripts\enable_ceo_briefing.bat ^(as Administrator^)
echo.
echo Briefings will be saved to:
echo   %VAULT_DIR%\Briefings\YYYY-MM-DD_CEO_Briefing.md
echo.
echo ============================================================================
echo.

pause
exit /b 0
