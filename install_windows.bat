@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 (echo Python 3.11+ necessario. & pause & exit /b 1)
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (echo Erro ao instalar dependencias. & pause & exit /b 1)
if not exist .env copy .env.example .env >nul
 echo Instalacao concluida. Executa iniciar_aura.bat
pause
