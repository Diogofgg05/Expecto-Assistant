import pytest
from aura.engine import normalized

def test_wake_words():
    assert normalized('Ativa Patronum!').rstrip('!') == 'ativa patronum'
    assert normalized('Expecto Patronum') == 'expecto patronum'

def test_public_identity():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert 'EXPECTO' in (root/'web/index.html').read_text()
    assert 'patronum' in (root/'web/app.js').read_text()
