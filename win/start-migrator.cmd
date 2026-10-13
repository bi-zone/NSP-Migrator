@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "RUNNER=%~dp0migrator-commands.ps1"

rem Double-click starts the production-like stack and opens Streamlit when ready.
if "%~1"=="" (
    echo [launcher] Starting the production stack. This window stays open until Streamlit starts.
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%RUNNER%" up -MODE prod
    set "MIGRATOR_EXIT_CODE=!ERRORLEVEL!"

    if not "!MIGRATOR_EXIT_CODE!"=="0" (
        echo.
        echo [launcher] Startup failed with exit code !MIGRATOR_EXIT_CODE!.
        pause
        exit /b !MIGRATOR_EXIT_CODE!
    )

    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%RUNNER%" open -MODE prod
    set "MIGRATOR_EXIT_CODE=!ERRORLEVEL!"

    if not "!MIGRATOR_EXIT_CODE!"=="0" (
        echo.
        echo [launcher] Browser launch failed with exit code !MIGRATOR_EXIT_CODE!.
        pause
    )

    exit /b !MIGRATOR_EXIT_CODE!
)

rem Explicit commands stay attached to the current terminal and preserve the exit code.
powershell.exe -NoLogo -NoProfile -File "%RUNNER%" %*
exit /b %ERRORLEVEL%
