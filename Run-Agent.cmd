@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_agent.ps1" %*
set exitcode=%ERRORLEVEL%

if not "%exitcode%"=="0" (
  echo.
  echo Launcher failed with exit code %exitcode%.
  echo See messages above for the fix.
  pause
)

exit /b %exitcode%
