@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Instala primeiro a AURA com install_windows.bat
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements-optimizer.txt
if errorlevel 1 (
  echo DSPy nao foi instalado; usa a AURA normalmente sem o otimizador.
  pause
  exit /b 1
)
echo Otimizador instalado. Executa: .venv\Scripts\python.exe -m aura.optimizer train
pause
