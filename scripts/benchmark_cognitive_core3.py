"""Offline deterministic smoke benchmark; NOT an Ollama intelligence score."""
import asyncio
import json
from aura.cognitive_core3 import run_cognitive_core
from aura.cognitive_semantic_verifier import make_semantic_verifier

CASES = [
    ("Explica isto", ["A água congela a zero graus Celsius sob pressão normal."], "A água congela a zero graus Celsius sob pressão normal.", True),
    ("Compara hipóteses", ["A Lua orbita a Terra."], "A Lua é feita de queijo.", False),
    ("Explica isto", [], "Resposta sem fontes.", False),
]

async def main():
    outcomes = []
    for question, evidence, answer, should_accept in CASES:
        async def model(prompt):
            return answer
        async def judge(prompt):
            return json.dumps({"verdict": "supported" if should_accept else "insufficient",
                               "evidence_ids": [0] if should_accept else []})
        result = await run_cognitive_core(question, model, evidence,
                                          verifier=make_semantic_verifier(judge))
        accepted = result["status"] == "externally_verified"
        outcomes.append({"expected_accept": should_accept, "accepted": accepted,
                         "pass": accepted == should_accept})
    print(json.dumps({"kind": "mock_smoke_test_not_model_benchmark",
                      "passed": sum(x["pass"] for x in outcomes),
                      "total": len(outcomes), "cases": outcomes}, indent=2))
    if not all(x["pass"] for x in outcomes):
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())
