@echo off
REM ============================================================================
REM setup_cloud_pull.bat - Cloud Pull Task Scheduler Configuration
REM ============================================================================
REM Configures Windows Task Scheduler to pull changes from cloud every 2 minutes.
REM This is for the CLOUD/SERVER machine that receives updates.
REM
REM IMPORTANT: Run this script as Administrator!
REM ============================================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================================================
echo   Cloud Vault Sync - Task Scheduler Configuration
echo ============================================================================
echo.

REM Check for administrator privileges
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] This script must be run as Administrator!
    echo.
    echo Please right-click on this script and select "Run as administrator".
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
REM Configuration - Edit these values for your setup
REM ============================================================================
set "REMOTE_URL=origin"
set "REMOTE_BRANCH=main"
set "TASK_NAME=PlatinumTierCloudPull"
set "PULL_INTERVAL=2"

echo [INFO] Configuration:
echo   Remote: %REMOTE_URL%
echo   Branch: %REMOTE_BRANCH%
echo   Pull Interval: Every %PULL_INTERVAL% minutes
echo.

REM ============================================================================
REM Step 1: Check prerequisites
REM ============================================================================
echo [1/5] Checking prerequisites...

where git >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Git is not installed or not in PATH.
    echo Please install Git from https://git-scm.com/download/win
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('git --version') do echo [OK] %%v

where schtasks >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] schtasks command not found.
    pause
    exit /b 1
)
echo [OK] Task Scheduler available.
echo.

REM ============================================================================
REM Step 2: Create the pull script
REM ============================================================================
echo [2/5] Creating cloud pull script...

set "PULL_SCRIPT=%VAULT_DIR%\scripts\cloud_pull.bat"

echo Creating: %PULL_SCRIPT%
(
    echo @echo off
    echo REM ============================================================================
    echo REM cloud_pull.bat - Automated Cloud Pull Script
    echo REM Called by Windows Task Scheduler every %PULL_INTERVAL% minutes
    echo REM ============================================================================
    echo.
    echo setlocal EnableDelayedExpansion
    echo.
    echo set "SCRIPT_DIR=%%~dp0"
    echo cd /d "%%SCRIPT_DIR%%.."
    echo.
    echo set "LOG_FILE=Logs\cloud_pull.log"
    echo set "ERROR_LOG=Logs\cloud_pull_errors.log"
    echo.
    echo REM Ensure Logs directory exists
    echo if not exist "Logs" mkdir "Logs"
    echo.
    echo REM Get timestamp
    echo for /f "tokens=2 delims==" %%i in ^('wmic os get localdatetime /value^') do set "dt=%%i"
    echo set "TIMESTAMP=!dt:~0,4!-!dt:~4,2!-!dt:~6,2! !dt:~8,2!:!dt:~10,2!:!dt:~12,2!"
    echo.
    echo REM Log start
    echo [!TIMESTAMP!] Starting cloud pull... ^>^> "!LOG_FILE!" 2^>^&1
    echo.
    echo REM Check if Git repository is initialized
    echo if not exist ".git" (
    echo     echo [!TIMESTAMP!] ERROR: Not a Git repository ^>^> "!LOG_FILE!" 2^>^&1
    echo     echo [!TIMESTAMP!] ERROR: Not a Git repository ^>^> "!ERROR_LOG!" 2^>^&1
    echo     exit /b 1
    echo )
    echo.
    echo REM Check for uncommitted local changes - stash them to prevent conflicts
    echo git diff --quiet --exit-code 2^>nul
    echo if %ERRORLEVEL% neq 0 (
    echo     echo [!TIMESTAMP!] Local changes detected - stashing... ^>^> "!LOG_FILE!" 2^>^&1
    echo     git stash push -m "Auto-stash before cloud pull !TIMESTAMP!" 2^>^> "!LOG_FILE!"
    echo     set "STASHED=1"
    echo ) else (
    echo     set "STASHED=0"
    echo )
    echo.
    echo REM Fetch from remote
    echo echo [!TIMESTAMP!] Fetching from remote... ^>^> "!LOG_FILE!" 2^>^&1
    echo git fetch %REMOTE_URL% %REMOTE_BRANCH% 2^>^> "!LOG_FILE!"
    echo if %ERRORLEVEL% neq 0 (
    echo     echo [!TIMESTAMP!] ERROR: Fetch failed ^>^> "!LOG_FILE!" 2^>^&1
    echo     echo [!TIMESTAMP!] ERROR: Fetch failed ^>^> "!ERROR_LOG!" 2^>^&1
    echo     REM Restore stashed changes if any
    echo     if "!STASHED!"=="1" git stash pop 2^>nul
    echo     exit /b 1
    echo )
    echo.
    echo REM Check if there are updates to pull
    echo git rev-parse HEAD > temp_local.txt
    echo git rev-parse %REMOTE_URL%/%REMOTE_BRANCH% > temp_remote.txt
    echo set /p LOCAL_HASH=^<temp_local.txt
    echo set /p REMOTE_HASH=^<temp_remote.txt
    echo del temp_local.txt temp_remote.txt 2^>nul
    echo.
    echo if "!LOCAL_HASH!"=="!REMOTE_HASH!" (
    echo     echo [!TIMESTAMP!] Already up to date ^>^> "!LOG_FILE!" 2^>^&1
    echo ) else (
    echo     echo [!TIMESTAMP!] Local: !LOCAL_HASH! ^>^> "!LOG_FILE!" 2^>^&1
    echo     echo [!TIMESTAMP!] Remote: !REMOTE_HASH! ^>^> "!LOG_FILE!" 2^>^&1
    echo     echo [!TIMESTAMP!] Pulling changes... ^>^> "!LOG_FILE!" 2^>^&1
    echo.
    echo     REM Use --strategy-option=theirs to prefer remote changes (cloud is source of truth)
    echo     git pull --strategy-option=theirs %REMOTE_URL% %REMOTE_BRANCH% 2^>^> "!LOG_FILE!"
    echo     if %ERRORLEVEL% neq 0 (
    echo         echo [!TIMESTAMP!] ERROR: Pull failed - attempting conflict resolution ^>^> "!LOG_FILE!" 2^>^&1
    echo         call scripts\resolve_conflicts.bat 2^>^> "!LOG_FILE!"
    echo     ) else (
    echo         echo [!TIMESTAMP!] Pull successful ^>^> "!LOG_FILE!" 2^>^&1
    echo     )
    echo )
    echo.
    echo REM Restore stashed changes if any (apply on top of pulled changes)
    echo if "!STASHED!"=="1" (
    echo     echo [!TIMESTAMP!] Restoring local changes... ^>^> "!LOG_FILE!" 2^>^&1
    echo     git stash pop 2^>^> "!LOG_FILE!"
    echo )
    echo.
    echo REM Log completion
    echo for /f "tokens=2 delims==" %%%%i in ^('wmic os get localdatetime /value^') do set "dt2=%%%%i"
    echo set "TIMESTAMP2=!dt2:~0,4!-!dt2:~4,2!-!dt2:~6,2! !dt2:~8,2!:!dt2:~10,2!:!dt2:~12,2!"
    echo [!TIMESTAMP2!] Cloud pull completed ^>^> "!LOG_FILE!" 2^>^&1
    echo.
    echo exit /b 0
) > "!PULL_SCRIPT!"

echo [OK] Pull script created.
echo.

REM ============================================================================
REM Step 3: Create conflict resolution script
REM ============================================================================
echo [3/5] Creating conflict resolution script...

set "RESOLVE_SCRIPT=%VAULT_DIR%\scripts\resolve_conflicts.bat"

if not exist "!RESOLVE_SCRIPT!" (
    echo Creating: %RESOLVE_SCRIPT%
    (
        echo @echo off
        echo REM ============================================================================
        echo REM resolve_conflicts.bat - Automatic Conflict Resolution
        echo REM Prefers remote changes for cloud sync
        echo REM ============================================================================
        echo.
        echo setlocal
        echo.
        echo echo Resolving conflicts (preferring remote)...
        echo.
        echo REM Get list of conflicted files
        echo for /f "tokens=*" %%%%i in ^('git diff --name-only --diff-filter=U 2^>nul^) do (
        echo     echo   Conflict: %%%%i
        echo     REM Keep remote version (theirs)
        echo     git checkout --theirs "%%%%i" 2^>nul
        echo     git add "%%%%i"
        echo )
        echo.
        echo REM Check if there are conflicts to resolve
        echo git diff --name-only --diff-filter=U 2^>nul ^| findstr . ^>nul
        echo if %ERRORLEVEL% neq 0 (
        echo     echo No conflicts found or all resolved.
        echo ) else (
        echo     echo Conflicts remain - manual intervention may be needed.
        echo )
        echo.
        echo exit /b 0
    ) > "!RESOLVE_SCRIPT!"
    echo [OK] Conflict resolution script created.
) else (
    echo [OK] Conflict resolution script already exists.
)
echo.

REM ============================================================================
REM Step 4: Delete existing task if present
REM ============================================================================
echo [4/5] Removing existing task (if any)...
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>nul
echo [OK] Previous task removed (if existed).
echo.

REM ============================================================================
REM Step 5: Create the scheduled task
REM ============================================================================
echo [5/5] Creating scheduled task...
echo.

REM Create task that runs every 2 minutes
schtasks /Create /TN "%TASK_NAME%" ^
    /TR "\"%PULL_SCRIPT%\"" ^
    /SC MINUTE ^
    /MO %PULL_INTERVAL% ^
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
REM Verification
REM ============================================================================
echo ============================================================================
echo   Configuration Complete!
echo ============================================================================
echo.
echo Task Details:
echo   Name: %TASK_NAME%
echo   Trigger: Every %PULL_INTERVAL% minutes
echo   Run As: SYSTEM (Highest privileges)
echo   Script: %PULL_SCRIPT%
echo.
echo To verify the task is working:
echo   1. Wait 2 minutes for first run
echo   2. Check Logs\cloud_pull.log
echo   3. Run: schtasks /Query /TN "%TASK_NAME%"
echo.
echo To view or modify the task:
echo   1. Open Task Scheduler (taskschd.msc)
echo   2. Find "%TASK_NAME%" in the task list
echo.
echo To run manually for testing:
echo   "%PULL_SCRIPT%"
echo.
echo To remove auto-pull:
echo   schtasks /Delete /TN "%TASK_NAME%" /F
echo.
echo ============================================================================
echo.

pause
exit /b 0
