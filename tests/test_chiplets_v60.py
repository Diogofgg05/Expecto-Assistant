"""Deterministic offline chiplet tests; no network, Ollama or accelerator."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest
from aura.chiplets import ChipletFabric


def test_standby_requires_no_initialisation_and_snapshot_is_inert():
    constructed = []
    fabric = ChipletFabric({'memory': lambda: constructed.append('memory') or object(),
                            'research': lambda: constructed.append('research') or object()})
    before = fabric.snapshot()
    assert before['active_count'] == 0
    assert before['standby'] == ['memory', 'research']
    assert constructed == []
    assert fabric.get('memory') is fabric.get('memory')
    assert constructed == ['memory']
    after = fabric.snapshot()
    assert after['active_count'] == 1
    assert after['calls']['memory'] == 2
    assert after['calls']['research'] == 0
    assert after['cold_start_ms']['memory'] >= 0


def test_dependency_can_reuse_single_instance():
    fabric = None
    fabric = ChipletFabric({'memory': lambda: object(),
                            'llm': lambda: {'memory': fabric.get('memory')}})
    llm = fabric.get('llm')
    assert llm['memory'] is fabric.get('memory')
    assert fabric.snapshot()['active'] == ['llm', 'memory']


def test_circular_dependency_does_not_poison_registry():
    fabric = None
    fabric = ChipletFabric({'loop': lambda: fabric.get('loop'),
                            'healthy': object})
    with pytest.raises(RuntimeError, match='Circular'):
        fabric.get('loop')
    assert fabric.snapshot()['failures']['loop'] == 1
    assert fabric.get('healthy') is fabric.get('healthy')


def test_factory_failure_can_retry_without_caching():
    attempts = []
    def build():
        attempts.append(None)
        if len(attempts) == 1:
            raise ValueError('offline dependency')
        return object()
    fabric = ChipletFabric({'memory': build})
    with pytest.raises(ValueError):
        fabric.get('memory')
    assert fabric.snapshot()['active_count'] == 0
    assert fabric.get('memory') is fabric.get('memory')
    assert len(attempts) == 2
    assert fabric.snapshot()['failures']['memory'] == 1


def test_concurrent_load_never_duplicates_services():
    calls = []
    barrier = threading.Barrier(12)
    def load():
        calls.append(1)
        time.sleep(0.01)
        return object()
    fabric = ChipletFabric({'research': load})
    def request():
        barrier.wait(timeout=5)
        return fabric.get('research')
    with ThreadPoolExecutor(max_workers=12) as pool:
        instances = list(pool.map(lambda _: request(), range(12)))
    assert len(calls) == 1
    assert all(x is instances[0] for x in instances)
    assert fabric.snapshot()['calls']['research'] == 12


def test_unknown_name_and_invalid_registry_rejected():
    with pytest.raises(AttributeError):
        ChipletFabric({'ok': object}).get('unknown')
    with pytest.raises(ValueError):
        ChipletFabric({'bad-name': object})
    with pytest.raises(ValueError):
        ChipletFabric({})


def test_engine_lazy_services_and_existing_routes(tmp_path):
    """Regression: simple UI commands must not load research or reasoning."""
    import asyncio
    from aura.config import Settings
    from aura.database import Database
    from aura.engine import AuraEngine

    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        auto_extract_memory=False)
    engine = AuraEngine(settings, Database(tmp_path / 'chiplet.sqlite3'))
    assert engine.chiplet_status()['active_count'] == 0
    response = asyncio.run(engine.command('Abre a memória'))
    assert response['action'] == {'type': 'open', 'panel': 'memory'}
    assert engine.chiplet_status()['active_count'] == 0
    assert engine.research is engine.research
    assert engine.chiplet_status()['active'] == ['research']
    status = asyncio.run(engine.command('estado dos chiplets'))
    assert status['data']['active_count'] == 1
    assert 'research' in status['data']['active']


def test_chiplet_status_api_is_read_only(tmp_path):
    from fastapi.testclient import TestClient
    from aura.config import Settings
    from aura.app import create_app

    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False,
                              auto_extract_memory=False))
    with TestClient(app) as client:
        r = client.get('/api/chiplets')
        assert r.status_code == 200
        assert r.json()['active_count'] == 0
        assert len(r.json()['standby']) >= 10


def test_memory_daemon_does_not_wake_expensive_services_when_idle(tmp_path):
    """Even when indexing and extraction are enabled, idle means no activation."""
    import asyncio
    from aura.config import Settings
    from aura.database import Database
    from aura.engine import AuraEngine

    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        embedding_model='unused-local-embedding',
                        auto_extract_memory=True)
    engine = AuraEngine(settings, Database(tmp_path / 'idle.sqlite3'))

    async def run_one_idle_cycle():
        stop = asyncio.Event()
        task = asyncio.create_task(engine.memory_daemon(stop))
        await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(run_one_idle_cycle())
    assert engine.chiplet_status()['active_count'] == 0
