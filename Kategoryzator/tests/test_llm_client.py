import os
import unittest
from unittest.mock import MagicMock, patch

from api import llm_client


class TestLLMClient(unittest.TestCase):
    def setUp(self):
        self._env_backup = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_disabled_returns_not_called(self):
        os.environ["LLM_FALLBACK_ENABLED"] = "0"
        result = llm_client.request_bedrock({"hello": "world"})
        self.assertFalse(result["called"])
        self.assertFalse(result["enabled"])

    @patch("boto3.client")
    def test_enabled_calls_bedrock_and_returns_text(self, mock_boto_client):
        os.environ["LLM_FALLBACK_ENABLED"] = "1"
        os.environ["LLM_BEDROCK_MODEL_ID"] = "anthropic.claude-3-haiku-20240307-v1:0"
        os.environ["LLM_AWS_REGION"] = "eu-central-1"

        client = MagicMock()
        client.converse.return_value = {
            "usage": {
                "inputTokens": 120,
                "outputTokens": 80,
                "totalTokens": 200,
            },
            "output": {
                "message": {
                    "content": [
                        {"text": "{\"final_prediction\": {\"kolumna_kpir\": \"OTHER_EXPENSES\"}, \"confidence\": 0.88}"}
                    ]
                }
            }
        }
        mock_boto_client.return_value = client

        result = llm_client.request_bedrock({"sample": "payload"})

        self.assertTrue(result["called"])
        self.assertTrue(result["enabled"])
        self.assertEqual(result["provider"], "aws-bedrock")
        self.assertIn("final_prediction", result["output_text"])
        self.assertEqual(result["usage"]["input_tokens"], 120)
        self.assertEqual(result["usage"]["output_tokens"], 80)
        self.assertEqual(result["usage"]["total_tokens"], 200)
        client.converse.assert_called_once()

    def test_enabled_without_model_raises(self):
        os.environ["LLM_FALLBACK_ENABLED"] = "1"
        os.environ.pop("LLM_BEDROCK_MODEL_ID", None)
        with self.assertRaises(RuntimeError):
            llm_client.request_bedrock({"sample": "payload"})


if __name__ == "__main__":
    unittest.main()
