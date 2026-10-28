# Expecto — instalacao Windows com SQLCipher

## Python suportado

Usa **Python 3.12 x64**. O instalador `install_windows.bat` seleciona explicitamente
`py -3.12`, recusa ambientes `.venv` criados com outras versoes e exige
um pacote SQLCipher binario (sem compilacao acidental com Conan/PyYAML).
Outras versoes de Python poderao funcionar no futuro, mas nao estao
confirmadas por este instalador.

1. Instala Python 3.12 de 64 bits e confirma `py -3.12 --version`.
2. Se a pasta `.venv` foi criada com Python 3.15, fecha o Expecto e
   renomeia a pasta para `.venv-python315-backup`.
3. Executa `install_windows.bat` na raiz do projeto.
4. O instalador valida `PRAGMA cipher_version` para garantir que a cifragem
   esta efetivamente presente.
5. Executa `iniciar_aura.bat` e usa a frase-passe de memoria habitual.

**Nunca apagues** a pasta `data`, nem desativas SQLCipher para contornar
a instalacao. Uma base cifrada nao se abre com SQLite normal. Uma frase-passe
perdida nao pode ser recuperada pelo instalador.

## Se o pacote binario nao existir

A linha de instalacao termina com erro controlado e deixa o ambiente
sem tentar compilar dependencias nativas. Verifica se tens efetivamente
Python 3.12 de 64 bits, atualiza pip e repete a instalacao.
A compilacao manual com Visual C++ nao e o caminho recomendado.

## Diagnostico rapido

```bat
py -3.12 --version
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pip --version
.venv\Scripts\python.exe -c "import sqlcipher3; print(sqlcipher3.connect(':memory:').execute('PRAGMA cipher_version').fetchone())"
```

Esta verificacao prova a presenca do backend SQLCipher, nao que uma
frase-passe de uma base existente esteja correta.
