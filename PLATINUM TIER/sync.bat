@echo off
REM ============================================================================
REM sync.bat - Git Vault Synchronization Script
REM ============================================================================
REM Synchronizes local vault changes with remote Git repository.
REM 
REM Usage:
REM   sync.bat              - Full sync (pull, then push)
REM   sync.bat pull         - Pull only from remote
REM   sync.bat push         - Push only to remote
REM   sync.bat status       - Show Git status
REM   sync.bat setup        - Initialize Git repository
REM ============================================================================

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "REMOTE=origin"
set "BRANCH=main"

REM ============================================================================
REM Parse command line arguments
REM ============================================================================
set "ACTION=sync"
if not "%~1"=="" set "ACTION=%~1"

goto :%ACTION% 2>nul || goto :help

REM ============================================================================
REM :setup - Initialize Git repository
REM ============================================================================
:setup
echo.
echo ============================================================================
echo   Git Repository Setup
echo ============================================================================
echo.

REM Check if already initialized
if exist ".git" (
    echo [INFO] Git repository already initialized.
    echo.
    git remote -v
    echo.
    choice /C YN /M "Do you want to reconfigure remote"
    if errorlevel 2 goto :status
)

REM Initialize Git
echo [INFO] Initializing Git repository...
git init

REM Configure user (prompt if not set)
git config user.name >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo.
    set /p GIT_USER="Enter your name for Git commits: "
    git config user.name "!GIT_USER!"
)

git config user.email >nul 2>nul
if %ERRORLEVEL% neq 0 (
    set /p GIT_EMAIL="Enter your email for Git commits: "
    git config user.email "!GIT_EMAIL!"
)

echo.
echo [OK] Git user configured.
echo.

REM Set up remote
echo [INFO] Remote repository URL:
echo   Example: https://github.com/username/platinum-vault.git
echo   Example: git@github.com:username/platinum-vault.git
echo.
set /p REMOTE_URL="Enter remote Git URL (or press Enter to skip): "
if not "!REMOTE_URL!"=="" (
    git remote add %REMOTE% "!REMOTE_URL!"
    echo [OK] Remote '%REMOTE%' added.
)

echo.
echo [INFO] Creating initial commit with current files...
git add .gitignore
git commit -m "Initial commit: Git configuration"

echo.
echo [OK] Git repository setup complete!
echo.
echo Next steps:
echo   1. Run: sync.bat push  (to push initial commit)
echo   2. On cloud machine: Run setup_cloud_pull.bat (as Administrator)
echo.
goto :end

REM ============================================================================
REM :pull - Pull changes from remote
REM ============================================================================
:pull
echo.
echo ============================================================================
echo   Pulling Changes from Remote
echo ============================================================================
echo.

REM Check if Git is initialized
if not exist ".git" (
    echo [ERROR] Git repository not initialized.
    echo Run: sync.bat setup
    goto :error
)

REM Check for uncommitted changes
git diff --quiet --exit-code 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARNING] You have uncommitted changes.
    echo.
    choice /C YN /M "Stash changes and continue"
    if errorlevel 2 (
        echo [INFO] Aborting pull.
        goto :status
    )
    echo [INFO] Stashing changes...
    git stash push -m "Manual stash before pull %DATE% %TIME%"
    set "STASHED=1"
) else (
    set "STASHED=0"
)

echo.
echo [INFO] Fetching from %REMOTE%/%BRANCH%...
git fetch %REMOTE% %BRANCH%

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Fetch failed. Check your connection and remote URL.
    if "!STASHED!"=="1" git stash pop 2>nul
    goto :error
)

REM Check if there are updates
git rev-parse HEAD > "%TEMP%\local.txt"
git rev-parse %REMOTE%/%BRANCH% > "%TEMP%\remote.txt"
set /p LOCAL_HASH=<"%TEMP%\local.txt"
set /p REMOTE_HASH=<"%TEMP%\remote.txt"
del "%TEMP%\local.txt" "%TEMP%\remote.txt" 2>nul

if "!LOCAL_HASH!"=="!REMOTE_HASH!" (
    echo [OK] Already up to date.
) else (
    echo [INFO] Local:  !LOCAL_HASH!
    echo [INFO] Remote: !REMOTE_HASH!
    echo.
    echo [INFO] Pulling changes (preferring remote for conflicts)...
    git pull --strategy-option=theirs %REMOTE% %BRANCH%
    
    if %ERRORLEVEL% neq 0 (
        echo.
        echo [ERROR] Pull failed - conflicts detected!
        echo See: sync.bat conflicts for resolution instructions.
        if "!STASHED!"=="1" git stash pop 2>nul
        goto :error
    )
    
    echo [OK] Pull successful.
)

REM Restore stashed changes
if "!STASHED!"=="1" (
    echo.
    echo [INFO] Restoring stashed changes...
    git stash pop
)

echo.
echo [OK] Pull complete.
goto :status

REM ============================================================================
REM :push - Push changes to remote
REM ============================================================================
:push
echo.
echo ============================================================================
echo   Pushing Changes to Remote
echo ============================================================================
echo.

REM Check if Git is initialized
if not exist ".git" (
    echo [ERROR] Git repository not initialized.
    echo Run: sync.bat setup
    goto :error
)

REM Show what will be pushed
echo [INFO] Current status:
git status --short
echo.

REM Check for uncommitted changes
git diff --quiet --exit-code 2>nul
git diff --cached --quiet --exit-code 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARNING] You have uncommitted changes.
    echo.
    choice /C YN /M "Commit changes before push"
    if errorlevel 2 (
        echo [INFO] Aborting push.
        goto :status
    )
    
    echo.
    set /p COMMIT_MSG="Enter commit message: "
    if "!COMMIT_MSG!"=="" set "COMMIT_MSG=Sync: Update vault"
    
    git add -A
    git commit -m "!COMMIT_MSG!"
)

REM Pull first to avoid conflicts
echo [INFO] Pulling latest changes before push...
git pull --rebase --strategy-option=theirs %REMOTE% %BRANCH% 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Rebase had conflicts - continuing with push...
)

echo.
echo [INFO] Pushing to %REMOTE%/%BRANCH%...
git push %REMOTE% %BRANCH%

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Push failed!
    echo Possible causes:
    echo   - Remote has changes you don't have (run: sync.bat pull)
    echo   - Network connection issue
    echo   - Authentication required
    goto :error
)

echo [OK] Push successful.
goto :status

REM ============================================================================
REM :sync - Full sync (pull then push)
REM ============================================================================
:sync
echo.
echo ============================================================================
echo   Full Vault Synchronization
echo ============================================================================
echo.

call :pull
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Sync failed at pull stage.
    goto :error
)

echo.
echo ---------------------------------------------------------------------------
echo.
call :push
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Sync failed at push stage.
    goto :error
)

echo.
echo ============================================================================
echo   [OK] Sync Complete!
echo ============================================================================
goto :end

REM ============================================================================
REM :status - Show Git status
REM ============================================================================
:status
echo.
echo ============================================================================
echo   Git Status
echo ============================================================================
echo.

if not exist ".git" (
    echo [INFO] Git repository not initialized.
    echo Run: sync.bat setup
    goto :end
)

echo [INFO] Remote: %REMOTE%
git remote get-url %REMOTE% 2>nul && echo.

echo [INFO] Current branch:
git branch --show-current
echo.

echo [INFO] Last commit:
git log -1 --pretty=format:"  %h - %s (%ar)" 
echo.
echo.

echo [INFO] Changes:
git status --short
if %ERRORLEVEL% equ 0 (
    echo   (no uncommitted changes)
)
echo.

echo [INFO] Ahead/Behind remote:
git rev-list --left-right --count HEAD...%REMOTE%/%BRANCH% 2>nul
if %ERRORLEVEL% equ 0 (
    for /f "tokens=1,2" %%a in ('git rev-list --left-right --count HEAD...%REMOTE%/%BRANCH% 2^>nul') do (
        echo   Ahead by: %%a commit(s)
        echo   Behind by: %%b commit(s)
    )
) else (
    echo   (unable to determine - run: sync.bat pull)
)
echo.

goto :end

REM ============================================================================
REM :conflicts - Show conflict resolution instructions
REM ============================================================================
:conflicts
echo.
echo ============================================================================
echo   Conflict Resolution Instructions
echo ============================================================================
echo.
echo [INFO] Conflicted files:
git diff --name-only --diff-filter=U
echo.
echo To resolve conflicts:
echo.
echo   1. View conflicted file:
echo      git diff -- conflicted_file.txt
echo.
echo   2. Choose resolution strategy:
echo.
echo      a) Accept remote version (cloud is source of truth):
echo         git checkout --theirs conflicted_file.txt
echo.
echo      b) Accept local version (keep your changes):
echo         git checkout --ours conflicted_file.txt
echo.
echo      c) Manual edit:
echo         notepad conflicted_file.txt
echo         (Remove conflict markers ^<^<^<^<^<^<^<, =======, ^>^>^>^>^>^>^>)
echo.
echo   3. Mark as resolved:
echo      git add conflicted_file.txt
echo.
echo   4. Complete the merge:
echo      git commit -m "Resolved conflicts"
echo.
echo   5. Or abort and retry:
echo      git merge --abort
echo      sync.bat pull
echo.
echo Quick resolve all (prefer remote):
echo   call scripts\resolve_conflicts.bat
echo.
goto :end

REM ============================================================================
REM :help - Show usage
REM ============================================================================
:help
echo.
echo ============================================================================
echo   Git Vault Sync - Usage
echo ============================================================================
echo.
echo   sync.bat              Full sync (pull, then push)
echo   sync.bat pull         Pull changes from remote only
echo   sync.bat push         Push changes to remote only
echo   sync.bat status       Show Git status
echo   sync.bat setup        Initialize Git repository
echo   sync.bat conflicts    Show conflict resolution help
echo.
echo ============================================================================

:end
endlocal
exit /b 0

:error
endlocal
exit /b 1
