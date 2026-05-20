import unittest

from scripts.orchestrator import orchestrate


class OrchestratorTest(unittest.TestCase):
    def test_q1_returns_all_keys(self):
        result = orchestrate("What is the duration of copyright protection for a work in Switzerland?")
        self.assertIn("enriched_context", result)
        self.assertIn("evidence", result)
        self.assertIn("answer", result)
        self.assertIn("viz_spec", result)

    def test_q1_answer_contains_markdown_sections(self):
        result = orchestrate("What is the duration of copyright protection for a work in Switzerland?")
        for section in ("Answer:", "Document:", "Reference:", "Evidence:"):
            self.assertIn(section, result["answer"])

    def test_q2_viz_type(self):
        result = orchestrate("Which economic rights does Germany recognize?")
        self.assertEqual(result["viz_spec"]["visualization_type"], "rights_list")

    def test_q3_viz_type(self):
        result = orchestrate("Does Italy provide a personal-use exception?")
        self.assertEqual(result["viz_spec"]["visualization_type"], "yes_no_exception")


if __name__ == "__main__":
    unittest.main()
