@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Primeiro executa install_windows.bat
  pause
  exit /b 1
)
.venv\Scripts\python.exe launch.py
pause
