import json
import unittest

from scripts.chatbot_query_context import process_user_query
from scripts.mock_kg_evidence import get_mock_evidence
from scripts.task2_answer_agent import generate_answer
from scripts.task3_viz_agent import generate_viz_spec, generate_viz_spec_json


class Task3VizAgentTest(unittest.TestCase):
    def _run(self, question: str, rule_type: str, jurisdiction: str) -> dict:
        ctx = process_user_query(question)
        evidence = get_mock_evidence(rule_type, jurisdiction)
        answer = generate_answer(question, ctx, evidence)
        return generate_viz_spec(question, ctx, evidence, answer)

    def test_copyright_duration_uses_rule_card(self):
        spec = self._run(
            "What is the duration of copyright protection for a work in Switzerland?",
            "copyright duration",
            "Switzerland",
        )
        self.assertEqual(spec["visualization_type"], "rule_card")
        self.assertEqual(spec["rule"]["type"], "copyright duration")
        self.assertEqual(spec["rule"]["normalized_value"], "life_plus_70")

    def test_economic_rights_uses_rights_list(self):
        spec = self._run(
            "Which economic rights does Germany recognize?",
            "economic rights",
            "Germany",
        )
        self.assertEqual(spec["visualization_type"], "rights_list")

    def test_personal_use_exception_uses_yes_no(self):
        spec = self._run(
            "Does Italy provide a personal-use exception?",
            "personal-use exception",
            "Italy",
        )
        self.assertEqual(spec["visualization_type"], "yes_no_exception")
        self.assertEqual(spec["rule"]["normalized_value"], "yes")

    def test_title_includes_jurisdiction(self):
        spec = self._run(
            "What is the duration of copyright protection for a work in Germany?",
            "copyright duration",
            "Germany",
        )
        self.assertIn("Germany", spec["title"])

    def test_highlight_fields_present(self):
        spec = self._run(
            "What is the duration of copyright protection for a work in Switzerland?",
            "copyright duration",
            "Switzerland",
        )
        self.assertIn("passage", spec["highlight"])
        self.assertIn("supporting_span", spec["highlight"])
        self.assertTrue(spec["highlight"]["passage"])

    def test_json_output_is_valid(self):
        ctx = process_user_query("Which economic rights does France recognize?")
        evidence = get_mock_evidence("economic rights", "France")
        answer = generate_answer("Which economic rights does France recognize?", ctx, evidence)
        raw = generate_viz_spec_json("Which economic rights does France recognize?", ctx, evidence, answer)
        parsed = json.loads(raw)
        self.assertIn("visualization_type", parsed)


if __name__ == "__main__":
    unittest.main()
