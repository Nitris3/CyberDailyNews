@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 or newer is required. Install Python from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

py -3 -c "import sys; raise SystemExit(0 if sys.version_info ^>= (3, 12) else 1)"
if errorlevel 1 (
  echo Python 3.12 or newer is required. Update Python, then run setup again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the private Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)

echo Installing Cyber Daily News...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto :failed

if not exist "config\ccip.local.yml" (
  copy /y "config\ccip.yml" "config\ccip.local.yml" >nul
)

echo Initializing the local database...
".venv\Scripts\python.exe" -m ccip.cli --config config\ccip.local.yml init-db
if errorlevel 1 goto :failed

echo Setup completed. Opening Cyber Daily News...
call Start-CyberDailyNews.cmd
exit /b 0

:failed
echo Setup did not complete. Review the message above, then run this file again.
pause
exit /b 1
