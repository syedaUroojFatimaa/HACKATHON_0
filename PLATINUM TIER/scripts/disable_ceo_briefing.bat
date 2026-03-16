@echo off
REM ============================================================================
REM disable_ceo_briefing.bat - Disable CEO Briefing Auto-Generation
REM ============================================================================

echo Disabling CEO briefing auto-generation...
schtasks /Delete /TN "PlatinumTierCEOBriefing" /F
if %ERRORLEVEL% equ 0 (
    echo [OK] CEO briefing task disabled.
) else (
    echo [ERROR] Failed to disable CEO briefing task.
    echo Task may not exist or requires Administrator privileges.
)
pause
