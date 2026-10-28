"""Static regression checks for the safety of the Windows installer."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def test_installer_pins_compatible_python_and_binary_sqlcipher():
    script=(ROOT/"install_windows.bat").read_text(encoding="utf-8")
    assert "py -3.12" in script
    assert "struct.calcsize('P') == 8" in script
    assert "--only-binary=sqlcipher3" in script
    assert "PRAGMA cipher_version" in script

def test_installer_never_deletes_data_or_existing_environment():
    script=(ROOT/"install_windows.bat").read_text(encoding="utf-8").lower()
    assert "rmdir " not in script
    assert "rd /s" not in script
    assert "del /" not in script
    assert "data\\" not in script
    assert "ren .venv .venv-antigo" in script  # instruction, not executed
