import asyncio
import unittest
from aura.cognitive_semantic_verifier import parse_judgement, make_semantic_verifier
from aura.cognitive_core3 import run_cognitive_core

class SemanticVerifierTests(unittest.TestCase):
    def test_invalid_json_fails_closed(self):
        self.assertEqual(parse_judgement("not json", 2)["verdict"], "unavailable")

    def test_out_of_range_citation_fails_closed(self):
        self.assertEqual(parse_judgement('{"verdict":"supported","evidence_ids":[8]}', 1)["verdict"], "unavailable")

    def test_boolean_citation_fails_closed(self):
        self.assertEqual(parse_judgement('{"verdict":"supported","evidence_ids":[true]}', 1)["verdict"], "unavailable")

    def test_all_claims_must_be_supported(self):
        async def judge(prompt):
            return ('{"verdict":"supported","evidence_ids":[0]}' if "Claim: \"Primeira.\"" in prompt
                    else '{"verdict":"insufficient","evidence_ids":[]}')
        verifier = make_semantic_verifier(judge)
        result = asyncio.run(verifier("Primeira. Segunda.", ["Primeira."]))
        self.assertEqual(result["verdict"], "insufficient")

    def test_supported_judge_contract(self):
        async def model(prompt):
            return "Primeira."
        async def judge(prompt):
            return '{"verdict":"supported","evidence_ids":[0]}'
        result = asyncio.run(run_cognitive_core("Explica isto", model, ["Primeira."],
                          verifier=make_semantic_verifier(judge)))
        self.assertEqual(result["status"], "externally_verified")

if __name__ == "__main__":
    unittest.main()
