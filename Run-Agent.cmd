@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_agent.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Run-Agent encountered an error (exit code %EXIT_CODE%).
    echo Review the messages above, fix the issue, then try again.
    pause
)

exit /b %EXIT_CODE%
