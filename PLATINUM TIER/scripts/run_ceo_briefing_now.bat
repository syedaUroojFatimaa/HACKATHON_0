@echo off
REM ============================================================================
REM run_ceo_briefing_now.bat - Generate CEO Briefing Immediately
REM ============================================================================

echo Running CEO briefing generation now...
echo.
cd /d "%~dp0.."

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python ceo_briefing.py --generate

echo.
echo Briefing saved to: Briefings\
echo.
pause
