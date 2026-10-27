from pathlib import Path
import pytest
from aura.database import Database
from aura.living_intelligence import ContinuityEngine

@pytest.fixture
def manager(tmp_path):
    return ContinuityEngine(Database(tmp_path / 'test.sqlite3'))

def test_explicit_experience_persists(manager, tmp_path):
    item=manager.remember('Testei o meu programa com um novo exercício.')
    fresh=ContinuityEngine(Database(tmp_path / 'test.sqlite3'))
    assert fresh.experiences()[0]['content']==item['content']
    assert fresh.experiences()[0]['verified']==0
    assert fresh.forget(item['id']) is True
    assert fresh.experiences()==[]

def test_goals_are_user_controlled(manager):
    goal=manager.add_goal('Estudar o livro sobre matrizes')
    assert manager.suggestions()[0]['action_requires_permission'] is True
    assert 'Estudar o livro' in manager.suggestions()[0]['suggestion']
    assert manager.goals()[0]['status']=='active'
    assert manager.goal_status(goal['id'],'done') is True
    assert manager.suggestions()==[]
    assert manager.goals()[0]['status']=='done'

def test_limits_and_no_implicit_memory(manager):
    assert manager.experiences()==[]
    assert manager.suggestions()==[]
    with pytest.raises(ValueError): manager.remember('a')
    with pytest.raises(ValueError): manager.add_goal('x'*181)
    with pytest.raises(ValueError): manager.goal_status('none','dangerous')

def test_context_does_not_assert_truth(manager):
    manager.remember('Vi uma afirmação que ainda não confirmei')
    assert 'não comprovados' in manager.context()
    assert 'Vi uma afirmação' in manager.context()
