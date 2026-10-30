"""Regression coverage for alias-aware Python inspection."""
from aura.code_inspection import inspect_python


def rules(source):
    return {item["rule"] for item in inspect_python(source)["findings"]}


def test_import_aliases_detected():
    source = ("import subprocess as sp\n"
              "from pickle import loads as decode\n"
              "import os as operating\n"
              "sp.run('x', shell=True)\n"
              "decode(b'x')\n"
              "operating.system('echo x')\n")
    assert rules(source) == {"shell-subprocess", "pickle-deserialization", "os-system"}


def test_direct_from_import_and_suggestions():
    inspected = inspect_python("from subprocess import run as execute\nexecute('ls',shell=True)\n")
    assert inspected["findings"][0]["rule"] == "shell-subprocess"
    assert inspected["findings"][0]["suggestion"]
    assert inspected["findings"][0]["line"] == 2


def test_no_user_code_execution(tmp_path):
    marker = tmp_path / "ran"
    inspected = inspect_python(f"open({str(marker)!r}, 'w').write('bad')\n")
    assert inspected["valid_syntax"] and not marker.exists()


def test_clean_code_no_findings():
    assert inspect_python("def add(x, y):\n    return x + y\n")["findings"] == []


def test_old_rules_preserved():
    assert rules("eval('2+2')\nexec('x=1')\ntry:\n pass\nexcept:\n pass\n") == {
        "dynamic-execution", "bare-except"}
