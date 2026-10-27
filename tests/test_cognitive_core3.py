import asyncio
import unittest
from aura.cognitive_core3 import CognitiveConfig, route_question, verify_answer, run_cognitive_core

class CognitiveCoreTests(unittest.TestCase):
    def test_route(self):
        self.assertEqual(route_question("Compara as hipóteses"), "deep")
        self.assertEqual(route_question("O que é álgebra?"), "fast")

    def test_no_false_certification(self):
        verdict = verify_answer("A Terra é plana", ["A Terra é plana"])
        self.assertFalse(verdict["accepted"])

    def test_missing_evidence_abstains(self):
        async def model(prompt):
            raise AssertionError("model should not run")
        result = asyncio.run(run_cognitive_core("Explica álgebra", model, []))
        self.assertEqual(result["status"], "abstained")

    def test_bounded_attempts(self):
        calls = []
        async def model(prompt):
            calls.append(prompt)
            return "Uma explicação provisória."
        result = asyncio.run(run_cognitive_core("Compara duas hipóteses", model, ["fonte"]))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["status"], "requires_review")

    def test_config_bounds(self):
        with self.assertRaises(ValueError):
            CognitiveConfig(max_attempts=100)

if __name__ == "__main__":
    unittest.main()
