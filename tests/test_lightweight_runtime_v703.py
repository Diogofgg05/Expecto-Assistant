"""EXPECTO 7.0.3: lazy audio services and identical cosine scoring."""
from __future__ import annotations

import importlib
import math

from fastapi.testclient import TestClient

from aura.config import Settings
from aura.memory import cosine


def test_optional_voice_engines_are_not_initialized_for_text_only(tmp_path, monkeypatch):
    module = importlib.import_module("aura.app")
    created = {"local": 0, "whisper": 0}

    class LocalStub:
        def __init__(self, settings):
            created["local"] += 1

        def capabilities(self):
            return {"local_stt": False, "local_tts": False}

    class WhisperStub:
        def __init__(self, settings):
            created["whisper"] += 1

        def capabilities(self):
            return {"persistent_stt": False}

    monkeypatch.setattr(module, "LocalVoice", LocalStub)
    monkeypatch.setattr(module, "PersistentWhisper", WhisperStub)
    app = module.create_app(
        Settings(data_dir=tmp_path, database_encryption_required=False)
    )
    assert created == {"local": 0, "whisper": 0}
    with TestClient(app) as client:
        assert client.get("/api/memory/status").status_code == 200
        assert client.get("/api/config").status_code == 200
        assert created == {"local": 0, "whisper": 0}
        for _ in range(3):
            result = client.get("/api/voice/capabilities")
            assert result.status_code == 200
            assert result.json()["persistent_stt"] is False
        assert created == {"local": 1, "whisper": 1}


def test_query_norm_precomputation_preserves_cosine_values():
    question = [0.13, -0.7, 0.8, 0.3, -0.2]
    norms = sum(x * x for x in question)
    vectors = [
        [0.2, 0.0, 0.9, -0.4, 0.1],
        [-1.1, 0.5, 0.8, 0.0, 0.9],
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [0.5, -0.6, 1.2, 0.25, 0.0],
    ]
    assert [cosine(question, vec, left_norm=norms) for vec in vectors] == [
        cosine(question, vec) for vec in vectors
    ]
    assert cosine([1.0], [1.0, 2.0], left_norm=1.0) == 0.0
    assert cosine([], [], left_norm=0.0) == 0.0
