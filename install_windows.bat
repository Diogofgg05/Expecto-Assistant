@echo off
setlocal
cd /d "%~dp0"
rem Prefer Python 3.12 for tested SQLCipher binary wheels.
where py >nul 2>&1
if %errorlevel%==0 (
    py -3.12 -m venv .venv
    if errorlevel 1 python -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 goto :install_error
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :install_error
call .venv\Scripts\python.exe -c "from aura.vault import sqlcipher_backend; assert sqlcipher_backend().connect(':memory:').execute('PRAGMA cipher_version').fetchone()[0]"
if errorlevel 1 goto :install_error
if not exist .env copy .env.example .env >nul
echo Instalacao concluida. Executa iniciar_aura.bat
if /I not "%~1"=="--ci" pause
exit /b 0
:install_error
echo Erro na instalacao ou SQLCipher indisponivel.
if /I not "%~1"=="--ci" pause
exit /b 1
