@echo off
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
  echo Run install.ps1 in the main folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py --project invoice --demo
pause
