import json
import unittest

from scripts.chatbot_query_context import process_user_query_json


class ChatbotQueryContextTest(unittest.TestCase):
    def test_copyright_duration_question(self):
        payload = json.loads(
            process_user_query_json(
                "What is the duration of copyright protection for a work in Switzerland?"
            )
        )

        self.assertEqual(payload["extracted_context"]["Jurisdiction"], "Switzerland")
        self.assertEqual(payload["extracted_context"]["Legal_Topic"], "copyright duration")

    def test_economic_rights_question(self):
        payload = json.loads(
            process_user_query_json("Which economic rights does Germany recognize?")
        )

        self.assertEqual(payload["extracted_context"]["Jurisdiction"], "Germany")
        self.assertEqual(payload["extracted_context"]["Legal_Topic"], "economic rights")

    def test_personal_use_exception_question(self):
        payload = json.loads(
            process_user_query_json("Does Italy provide a personal-use exception?")
        )

        self.assertEqual(payload["extracted_context"]["Jurisdiction"], "Italy")
        self.assertEqual(
            payload["extracted_context"]["Legal_Topic"],
            "personal-use exception",
        )


if __name__ == "__main__":
    unittest.main()
