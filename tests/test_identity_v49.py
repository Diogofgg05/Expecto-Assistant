from aura.identity import Identity, IdentitySettings
import pytest

def test_identity_constancy():
    p = Identity().prompt('cientifico')
    assert 'Expecto' in p and 'não é uma pessoa' in p
    assert 'hipóteses' in p

def test_style_persistence(tmp_path):
    s = IdentitySettings(tmp_path)
    assert s.mode() == 'equilibrado'
    s.set_mode('professor')
    assert IdentitySettings(tmp_path).mode() == 'professor'
    assert 'Ensina por passos' in Identity().prompt(s.mode())

def test_invalid_mode_does_not_modify(tmp_path):
    s=IdentitySettings(tmp_path)
    s.set_mode('criativo')
    with pytest.raises(ValueError):
        s.set_mode('admin')
    assert s.mode() == 'criativo'

def test_corruption_fallback(tmp_path):
    s=IdentitySettings(tmp_path)
    s.path.write_text('{invalid')
    assert s.mode() == 'equilibrado'
