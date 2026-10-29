"""Performance 4.3: local DB context preparation overlaps retrieval.

This is a deterministic scheduling test, not a real-hardware speed measurement.
"""
import asyncio
import threading

from aura.config import Settings
from aura.llm import Ollama


def test_local_context_preparation_overlaps_semantic_retrieval(tmp_path):
    local_finished = threading.Event()

    class MockMemory:
        model = "test"
        async def recall_pair(self, question, **kwargs):
            # The independent local metadata lookup must run concurrently,
            # rather than waiting until after an artificial embedding delay.
            assert await asyncio.to_thread(local_finished.wait, 2.0)
            return [], []

    llm = Ollama(Settings(data_dir=tmp_path, database_encryption_required=False),
                 object(), MockMemory())

    def fetch_local(question):
        assert question == "Qual era o meu projeto?"
        local_finished.set()
        return [], [], [], [], [], "", ""
    llm._local_context_parts = fetch_local

    async def run():
        context, continuity, reflection = await llm._personal_context(
            "Qual era o meu projeto?")
        assert "Memórias do utilizador" in context
        assert continuity == reflection == ""
    asyncio.run(asyncio.wait_for(run(), 3.0))


def test_context_failure_does_not_persist_private_text(tmp_path):
    class NoMemory:
        model = ""
        async def recall(self, *args):
            return []
        async def recall_episodes(self, *args):
            return []

    llm = Ollama(Settings(data_dir=tmp_path, database_encryption_required=False),
                 object(), NoMemory())
    llm._local_context_parts = lambda question: ([], [], [], [], [], "", "")
    context, _, _ = asyncio.run(llm._personal_context("Como está a minha memória?"))
    assert "Como está a minha memória?" not in context
    assert "Memórias do utilizador" in context
