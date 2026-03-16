@echo off
REM ============================================================================
REM setup_workzones.bat - Cloud vs Local Work-Zone Architecture Setup
REM ============================================================================
REM Creates the folder structure for separated Cloud/Local responsibilities
REM ============================================================================

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR_DIR%.."

echo.
echo ============================================================================
echo   Cloud vs Local Work-Zone Architecture Setup
echo ============================================================================
echo.
echo Creating folder structure...
echo.

REM ============================================================================
REM Core Work Zones
REM ============================================================================

REM Needs_Action subdirectories (by channel)
echo [1/8] Creating Needs_Action work zones...
if not exist "Needs_Action" mkdir "Needs_Action"
if not exist "Needs_Action\email" mkdir "Needs_Action\email"
if not exist "Needs_Action\social" mkdir "Needs_Action\social"
if not exist "Needs_Action\general" mkdir "Needs_Action\general"
echo   [OK] Needs_Action\email\
echo   [OK] Needs_Action\social\
echo   [OK] Needs_Action\general\

REM Pending_Approval subdirectories (by channel)
echo [2/8] Creating Pending_Approval work zones...
if not exist "Pending_Approval" mkdir "Pending_Approval"
if not exist "Pending_Approval\email" mkdir "Pending_Approval\email"
if not exist "Pending_Approval\social" mkdir "Pending_Approval\social"
if not exist "Pending_Approval\general" mkdir "Pending_Approval\general"
echo   [OK] Pending_Approval\email\
echo   [OK] Pending_Approval\social\
echo   [OK] Pending_Approval\general\

REM Approved (completed approvals)
echo [3/8] Creating Approved archive...
if not exist "Approved" mkdir "Approved"
if not exist "Approved\email" mkdir "Approved\email"
if not exist "Approved\social" mkdir "Approved\social"
if not exist "Approved\general" mkdir "Approved\general"
echo   [OK] Approved\email\
echo   [OK] Approved\social\
echo   [OK] Approved\general\

REM In_Progress work zones (Cloud vs Local)
echo [4/8] Creating In_Progress work zones...
if not exist "In_Progress" mkdir "In_Progress"
if not exist "In_Progress\cloud" mkdir "In_Progress\cloud"
if not exist "In_Progress\local" mkdir "In_Progress\local"
echo   [OK] In_Progress\cloud\
echo   [OK] In_Progress\local\

REM ============================================================================
REM Legacy Compatibility Folders
REM ============================================================================

echo [5/8] Creating legacy compatibility folders...
if not exist "Inbox" mkdir "Inbox"
if not exist "Done" mkdir "Done"
if not exist "Errors" mkdir "Errors"
if not exist "Plans" mkdir "Plans"
if not exist "Reports" mkdir "Reports"
if not exist "Accounting" mkdir "Accounting"
echo   [OK] Inbox\
echo   [OK] Done\
echo   [OK] Errors\
echo   [OK] Plans\
echo   [OK] Reports\
echo   [OK] Accounting\

REM ============================================================================
REM Logs and State
REM ============================================================================

echo [6/8] Creating Logs folder...
if not exist "Logs" mkdir "Logs"
echo   [OK] Logs\

REM ============================================================================
REM Create Zone State Files
REM ============================================================================

echo [7/8] Creating zone state files...

REM Cloud zone state
if not exist "In_Progress\cloud\.zone_owner" (
    echo CLOUD
    echo.
    echo Responsibilities:
    echo - Email triage
    echo - Draft replies
    echo - Draft social posts
    echo - Write approval files only
) > "In_Progress\cloud\.zone_owner"

REM Local zone state
if not exist "In_Progress\local\.zone_owner" (
    echo LOCAL
    echo.
    echo Responsibilities:
    echo - Final send/post actions
    echo - WhatsApp session
    echo - Payments
    echo - Approvals
) > "In_Progress\local\.zone_owner"

REM Zone lock file (prevents concurrent claims)
if not exist "In_Progress\.zone_lock" (
    echo {}
) > "In_Progress\.zone_lock"

echo   [OK] In_Progress\cloud\.zone_owner
echo   [OK] In_Progress\local\.zone_owner
echo   [OK] In_Progress\.zone_lock

REM ============================================================================
REM Update .gitignore for work zones
REM ============================================================================

echo [8/8] Updating .gitignore for work zones...

REM Check if .gitignore exists
if not exist ".gitignore" (
    echo [WARNING] .gitignore not found - creating basic one
    echo.
    echo .env
    echo tokens/
    echo sessions/
    echo Logs/
) > ".gitignore"

REM Add work-zone specific ignores if not present
findstr /C:"In_Progress/cloud/*.lock" ".gitignore" >nul 2>nul
if errorlevel 1 (
    echo.
    echo REM Work zone lock files
    echo In_Progress/cloud/*.lock
    echo In_Progress/local/*.lock
    echo In_Progress/.zone_lock
) >> ".gitignore"

echo   [OK] .gitignore updated

REM ============================================================================
REM Summary
REM ============================================================================

echo.
echo ============================================================================
echo   Work-Zone Architecture Setup Complete!
echo ============================================================================
echo.
echo Folder Structure:
echo.
echo   Needs_Action/           # New tasks awaiting processing
echo   ├── email/              # Email-related tasks
echo   ├── social/             # Social media tasks
echo   └── general/            # Other tasks
echo.
echo   Pending_Approval/       # Awaiting human approval
echo   ├── email/              # Email drafts for approval
echo   ├── social/             # Social posts for approval
echo   └── general/            # Other approvals
echo.
echo   In_Progress/            # Currently being worked on
echo   ├── cloud/              # Cloud is working (claim-by-move)
echo   └── local/              # Local is working (claim-by-move)
echo.
echo   Approved/               # Approved and completed
echo   ├── email/
echo   ├── social/
echo   └── general/
echo.
echo Rules:
echo   1. Claim-by-Move: Move file to your zone to claim it
echo   2. Single-Writer: Only one zone writes to Dashboard.md
echo   3. Cloud writes approval files only
echo   4. Local performs final actions
echo.
echo Next Steps:
echo   - Cloud: Run scripts\cloud_worker.bat
echo   - Local: Run scripts\local_worker.bat
echo.
echo ============================================================================
echo.

pause
exit /b 0
