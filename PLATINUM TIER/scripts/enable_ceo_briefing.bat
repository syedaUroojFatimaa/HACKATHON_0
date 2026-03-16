@echo off
REM ============================================================================
REM enable_ceo_briefing.bat - Re-enable CEO Briefing Auto-Generation
REM ============================================================================

net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Run as Administrator!
    pause
    exit /b 1
)

cd /d "%~dp0.."
call scripts\setup_ceo_briefing.bat
