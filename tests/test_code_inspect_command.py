"""Natural-language programming commands must be read-only and deterministic."""
import asyncio
from aura.engine import AuraEngine


def test_inspect_python_command_without_model_or_database():
    engine = AuraEngine.__new__(AuraEngine)
    result = asyncio.run(engine.command(
        "analisa código Python:\n```python\nimport subprocess\nsubprocess.run('x',shell=True)\n```"))
    assert result['ok']
    assert not result['spoken']
    inspection = result['data']['code_inspection']
    assert inspection['valid_syntax']
    assert [item['rule'] for item in inspection['findings']] == ['shell-subprocess']


def test_inspect_python_command_never_executes(tmp_path):
    engine = AuraEngine.__new__(AuraEngine)
    marker = tmp_path / 'executed.txt'
    command = "verifica código: open(" + repr(str(marker)) + ", 'w').write('unsafe')"
    result = asyncio.run(engine.command(command))
    assert result['ok']
    assert not marker.exists()
    assert result['data']['code_inspection']['verification'] == 'static_heuristics_no_execution'


def test_inspect_python_command_rejects_oversized_source():
    engine = AuraEngine.__new__(AuraEngine)
    result = asyncio.run(engine.command("analisa código: " + ("x" * 150001)))
    assert result['ok']
    assert result['spoken'] == ''
    assert 'demasiado' in result['text']
