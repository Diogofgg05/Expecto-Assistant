"""Regression tests for concurrent external searches (no external network)."""
import asyncio
import time
from aura.reasoning_orchestrator import ReasoningOrchestrator


class StubResearch:
    async def investigate(self, *args, **kwargs):
        return {"evidence": []}


class StubModel:
    async def __call__(self, prompt):
        return {"queries": ["alternate research query"]}


class StubExternal:
    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def search(self, query, limit=5):
        self.active += 1
        self.max_active = max(self.active, self.max_active)
        try:
            await asyncio.sleep(0.025)
            return [{"url": "https://example.com/" + query.replace(" ", "-"),
                     "title": query, "content": "An unverified preview."}]
        finally:
            self.active -= 1


def test_external_searches_are_concurrent_and_ordered():
    external = StubExternal()
    result = asyncio.run(ReasoningOrchestrator(None, StubModel(),
                      external=external, research=StubResearch()).run("research query"))
    assert external.max_active == 2
    assert result["research_queries"] == ["research query", "alternate research query"]
    assert [item["title"] for item in result["evidence"]] == [
        "research query", "alternate research query"]
    assert result["status"] == "abstained"  # Mocked previews are not verified truth.


class FailingExternal:
    async def search(self, query, limit=5):
        if query == "research query":
            raise TimeoutError("simulated timeout")
        return [{"url":"https://example.org/doc", "title":"second",
                 "content":"preview"}]


def test_failed_external_lookup_preserves_other_results():
    result = asyncio.run(ReasoningOrchestrator(None, StubModel(),
                    external=FailingExternal(), research=StubResearch()).run("research query"))
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["title"] == "second"
    assert any("TimeoutError" in value for value in result["limitations"])
