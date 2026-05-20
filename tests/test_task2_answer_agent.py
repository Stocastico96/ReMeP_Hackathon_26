import unittest

from scripts.chatbot_query_context import process_user_query
from scripts.mock_kg_evidence import get_mock_evidence
from scripts.task2_answer_agent import generate_answer


class Task2AnswerAgentTest(unittest.TestCase):
    def test_copyright_duration_switzerland(self):
        question = "What is the duration of copyright protection for a work in Switzerland?"
        ctx = process_user_query(question)
        evidence = get_mock_evidence("copyright duration", "Switzerland")
        answer = generate_answer(question, ctx, evidence)

        self.assertIn("Answer:", answer)
        self.assertIn("Document:", answer)
        self.assertIn("Reference:", answer)
        self.assertIn("Evidence:", answer)
        self.assertIn("<u>", answer)
        self.assertIn("70 years", answer)

    def test_economic_rights_germany(self):
        question = "Which economic rights does Germany recognize?"
        ctx = process_user_query(question)
        evidence = get_mock_evidence("economic rights", "Germany")
        answer = generate_answer(question, ctx, evidence)

        self.assertIn("Document:", answer)
        self.assertIn("<u>", answer)

    def test_personal_use_exception_italy(self):
        question = "Does Italy provide a personal-use exception?"
        ctx = process_user_query(question)
        evidence = get_mock_evidence("personal-use exception", "Italy")
        answer = generate_answer(question, ctx, evidence)

        self.assertIn("Answer:", answer)
        self.assertIn("<u>", answer)

    def test_empty_evidence_returns_no_result_notice(self):
        question = "What is the copyright term in Narnia?"
        ctx = process_user_query(question)
        evidence = {
            "answer_candidate": "",
            "rule_type": "copyright duration",
            "normalized_rule": {},
            "document": {"title": "", "uri": "", "local_path": ""},
            "reference": {},
            "passage": "",
            "supporting_span": "",
        }
        answer = generate_answer(question, ctx, evidence)

        self.assertIn("KG did not return", answer)


if __name__ == "__main__":
    unittest.main()
