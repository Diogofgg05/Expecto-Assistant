@echo off
setlocal
cd /d "%~dp0"

rem Expecto Windows installer: Python 3.12 x64 is required for SQLCipher wheels.
rem Never delete or overwrite an existing virtual environment or user data.
py -3.12 -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Necessitas de Python 3.12 de 64 bits.
    echo Instala a partir de https://www.python.org/downloads/
    echo Confirma com: py -3.12 --version
    echo O Python 3.15 nao tem wheel SQLCipher compativel nesta configuracao.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [ERRO] A pasta .venv usa outra versao de Python.
        echo Fecha a aplicacao e renomeia: ren .venv .venv-antigo
        echo Volta a executar este instalador. Nao apagues a pasta data.
        pause
        exit /b 1
    )
) else (
    if exist ".venv" (
        echo [ERRO] Existe uma pasta .venv incompleta ou inesperada.
        echo Renomeia-a manualmente antes de instalar. Nada foi apagado.
        pause
        exit /b 1
    )
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel criar o ambiente Python 3.12.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :install_error
rem Never build SQLCipher from source implicitly; fail clearly if wheel unavailable.
".venv\Scripts\python.exe" -m pip install --only-binary=sqlcipher3 -r requirements.txt
if errorlevel 1 goto :install_error
".venv\Scripts\python.exe" -c "import sqlcipher3; c=sqlcipher3.connect(':memory:'); v=c.execute('PRAGMA cipher_version').fetchone(); assert v and v[0], 'SQLCipher indisponivel'; print('SQLCipher operacional:',v[0]); c.close()"
if errorlevel 1 goto :install_error

if not exist ".env" copy ".env.example" ".env" >nul
echo [OK] Instalacao concluida com SQLCipher ativo.
echo Executa iniciar_aura.bat
pause
exit /b 0

:install_error
echo [ERRO] Falha na instalacao ou verificacao do SQLCipher.
echo Confirma Python 3.12 x64 e os requisitos da versao.
echo A base de dados nao foi modificada. Nao desatives a cifragem.
pause
exit /b 1
