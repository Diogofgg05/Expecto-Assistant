from pathlib import Path
import argparse
import pytest
from aura.reward_lab import arithmetic_reward
from importlib.util import spec_from_file_location, module_from_spec


def test_arithmetic_reward_exact():
    case={'kind':'exact_arithmetic','expression':'(125+75)/2'}
    assert arithmetic_reward(case,{'result':'100'})['reward']==1.0
    assert arithmetic_reward(case,{'result':'99'})['reward']==0.0


def test_arithmetic_reward_no_execution():
    assert arithmetic_reward({'kind':'exact_arithmetic','expression':'__import__("os").system("echo hi")'},
                             {'result':'123'})['reward']==0.0
    with pytest.raises(ValueError): arithmetic_reward({'kind':'medicine'}, {'result':'true'})


def test_trainer_requires_approval(tmp_path):
    file=Path(__file__).resolve().parents[1]/'scripts'/'train_local_lora.py'
    spec=spec_from_file_location('expecto_train',file);module=module_from_spec(spec);spec.loader.exec_module(module)
    args=argparse.Namespace(dataset=str(tmp_path/'dataset'),model=str(tmp_path/'model'),output=str(tmp_path/'out'),
                            mode='sft',approve_training=False)
    with pytest.raises(PermissionError):module.validate_paths(args)
