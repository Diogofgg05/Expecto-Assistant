"""Optional DSPy integration contract smoke test; never contacts Ollama."""
import pytest
from aura.config import Settings
from aura.database import Database
from aura.optimizer import OptimizationLab, load_benchmark


def test_real_dspy_labeled_optimizer_roundtrip_if_available(tmp_path):
    dspy=pytest.importorskip('dspy')
    settings=Settings(data_dir=tmp_path,database_encryption_required=False)
    lab=OptimizationLab(settings,Database(tmp_path/'aura.sqlite3'))
    train=lab._examples(dspy,load_benchmark()['train'])
    candidate=dspy.LabeledFewShot(k=2).compile(lab._program(dspy),trainset=train,sample=False)
    assert candidate is not None
    output=tmp_path/'candidate.json'
    candidate.save(str(output),save_program=False)
    program=lab._program(dspy)
    program.load(str(output))
    assert output.read_text(encoding='utf-8').startswith('{')
