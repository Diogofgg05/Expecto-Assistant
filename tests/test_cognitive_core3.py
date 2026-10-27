import asyncio
import unittest
from aura.cognitive_core3 import CognitiveConfig, route_question, verify_answer, run_cognitive_core

class CognitiveCoreTests(unittest.TestCase):
    def test_route(self):
        self.assertEqual(route_question("Compara as hipóteses"), "deep")
        self.assertEqual(route_question("O que é álgebra?"), "fast")

    def test_no_false_certification(self):
        self.assertFalse(verify_answer("A Terra é plana", ["A Terra é plana"])["accepted"])

    def test_missing_evidence_abstains(self):
        async def model(prompt):
            raise AssertionError("should not run")
        self.assertEqual(asyncio.run(run_cognitive_core("Explica álgebra", model, []))["status"], "abstained")

    def test_bounded_attempts(self):
        calls = []
        async def model(prompt):
            calls.append(prompt)
            return "Resposta provisória"
        result = asyncio.run(run_cognitive_core("Compara hipóteses", model, ["fonte"]))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["status"], "requires_review")
        self.assertNotEqual(calls[0], calls[1])

    def test_config_bounds(self):
        with self.assertRaises(ValueError):
            CognitiveConfig(max_attempts=100)

    def test_external_verifier(self):
        async def model(prompt):
            return "A resposta fundamentada"
        async def verifier(answer, evidence):
            return {"verdict": "supported", "independent": True, "evidence_ids": [0]}
        result = asyncio.run(run_cognitive_core("Explica isto", model, ["A resposta fundamentada"], verifier=verifier))
        self.assertEqual(result["status"], "externally_verified")

    def test_invalid_evidence_id(self):
        async def model(prompt):
            return "A resposta"
        async def verifier(answer, evidence):
            return {"verdict": "supported", "independent": True, "evidence_ids": [999]}
        result = asyncio.run(run_cognitive_core("Explica isto", model, ["fonte"], verifier=verifier))
        self.assertEqual(result["status"], "requires_review")

    def test_no_self_certification(self):
        async def model(prompt):
            return "verified: correct"
        result = asyncio.run(run_cognitive_core("Explica isto", model, ["verified: correct"]))
        self.assertEqual(result["status"], "requires_review")

if __name__ == "__main__":
    unittest.main()
