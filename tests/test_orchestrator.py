"""Tests for the parts of the pipeline that do not depend on the LLM.

The previous version asserted both the deterministic answer format ("Answer:",
"Document:", …) and an LLM-derived visualization type, so it could never pass in
one run: with an API key configured the first assertion failed, without one the
second did. The symbolic layer is tested directly instead, which is also the
layer the compliance claim rests on.

Run:
    PYTHONPATH=. uv run python tests/test_orchestrator.py
"""

import unittest

from scripts.chatbot_query_context import SPARQL_ENRICHMENT_PHRASE
from scripts.kg_query import query_kg
from scripts.orchestrator import orchestrate
from scripts.pydantic_models import SPARQLParams
from scripts.task2_answer_agent import generate_answer
from scripts.task3_viz_agent import generate_viz_spec


def _context(jurisdiction: str, topic: str) -> dict:
    return {
        "extracted_context": {
            "User_Objective": "test",
            "Time_Frame": "Current",
            "Jurisdiction": jurisdiction,
            "Legal_Topic": topic,
        },
        "enriched_query": f"test {SPARQL_ENRICHMENT_PHRASE}",
    }


def _evidence(jurisdiction: str, topic: str):
    ctx = _context(jurisdiction, topic)["extracted_context"]
    return query_kg(SPARQLParams.from_enriched(ctx))


class OrchestratorTest(unittest.TestCase):
    def test_returns_all_keys(self):
        result = orchestrate("What is the duration of copyright protection in Switzerland?")
        for key in ("enriched_context", "evidence", "answer", "viz_spec"):
            self.assertIn(key, result)


class KGRetrievalTest(unittest.TestCase):
    def test_duration_evidence_cites_the_article(self):
        evidence = _evidence("Switzerland", "copyright duration")
        self.assertEqual(evidence["reference"]["article"], "Art. 29 URG")
        self.assertTrue(evidence["passage"], "expected a passage from the AKN document")

    def test_rights_evidence_lists_the_rights(self):
        evidence = _evidence("Germany", "economic rights")
        self.assertIn("reproduction", evidence["answer_candidate"].lower())

    def test_eu_rules_come_from_two_directives(self):
        duration  = _evidence("EU", "copyright duration")
        exception = _evidence("EU", "personal-use exception")
        self.assertIn("2006", duration["document"]["title"])
        self.assertIn("InfoSoc", exception["document"]["title"])


class AnswerAgentTest(unittest.TestCase):
    """The deterministic formatter used whenever the LLM is unavailable."""

    def test_answer_contains_markdown_sections(self):
        context  = _context("Switzerland", "copyright duration")
        evidence = _evidence("Switzerland", "copyright duration")
        answer   = generate_answer("How long does copyright last in Switzerland?",
                                   context, evidence)
        for section in ("Answer:", "Document:", "Reference:", "Evidence:"):
            self.assertIn(section, answer)


class VizSpecTest(unittest.TestCase):
    def test_duration_gives_a_rule_card(self):
        spec = self._spec("Switzerland", "copyright duration")
        self.assertEqual(spec["visualization_type"], "rule_card")

    def test_rights_give_a_list(self):
        spec = self._spec("Germany", "economic rights")
        self.assertEqual(spec["visualization_type"], "rights_list")

    def test_exception_gives_a_yes_no_card(self):
        spec = self._spec("Italy", "personal-use exception")
        self.assertEqual(spec["visualization_type"], "yes_no_exception")

    def _spec(self, jurisdiction: str, topic: str) -> dict:
        context  = _context(jurisdiction, topic)
        evidence = _evidence(jurisdiction, topic)
        return generate_viz_spec("test", context, evidence, "")


class ComplianceTest(unittest.TestCase):
    """The verdict the paper rests on — computed without any LLM."""

    def test_all_nine_jurisdictions_meet_the_berne_floor(self):
        from scripts.kg_query import check_compliance, list_countries
        for country in list_countries():
            with self.subTest(country=country["code"]):
                result = check_compliance(country["code"])
                self.assertNotIn("error", result)
                self.assertTrue(result["compliant"])
                self.assertGreaterEqual(result["country_duration_years"], 50)

    def test_new_zealand_sits_exactly_on_the_floor(self):
        from scripts.kg_query import check_compliance
        result = check_compliance("NZ")
        self.assertEqual(result["country_duration_years"], 50)
        self.assertEqual(result["margin_years"], 0)


if __name__ == "__main__":
    unittest.main()
