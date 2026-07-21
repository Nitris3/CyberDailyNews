@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo Python environment not found. Complete the installation steps first.
  pause
  exit /b 1
)

if not exist "config\ccip.local.yml" (
  copy /y "config\ccip.yml" "config\ccip.local.yml" >nul
)

start "Cyber Daily News" ".venv\Scripts\pythonw.exe" -m ccip.cli --config config\ccip.local.yml dashboard
endlocal
