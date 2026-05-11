import os
import unittest
from unittest.mock import MagicMock, patch

from api import llm_client


class TestLlmContracts(unittest.TestCase):
    def setUp(self):
        self._env_backup = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_disabled_contract_shape(self):
        os.environ["LLM_FALLBACK_ENABLED"] = "0"
        result = llm_client.request_bedrock({"x": 1})

        self.assertEqual(set(result.keys()), {"called", "enabled", "reason"})
        self.assertFalse(result["called"])
        self.assertFalse(result["enabled"])
        self.assertIsInstance(result["reason"], str)

    @patch("boto3.client")
    def test_enabled_contract_shape(self, mock_boto_client):
        os.environ["LLM_FALLBACK_ENABLED"] = "1"
        os.environ["LLM_BEDROCK_MODEL_ID"] = "anthropic.claude-3-haiku-20240307-v1:0"
        os.environ["LLM_AWS_REGION"] = "eu-central-1"

        client = MagicMock()
        client.converse.return_value = {
            "usage": {
                "inputTokens": 11,
                "outputTokens": 7,
                "totalTokens": 18,
            },
            "output": {
                "message": {
                    "content": [{"text": "{\"confidence\": 0.8}"}]
                }
            },
        }
        mock_boto_client.return_value = client

        result = llm_client.request_bedrock({"payload": True})

        self.assertTrue(result["called"])
        self.assertTrue(result["enabled"])
        self.assertEqual(result["provider"], "aws-bedrock")
        self.assertEqual(result["region"], "eu-central-1")
        self.assertEqual(result["model_id"], "anthropic.claude-3-haiku-20240307-v1:0")
        self.assertIn("output_text", result)
        self.assertIn("usage", result)
        self.assertEqual(set(result["usage"].keys()), {"input_tokens", "output_tokens", "total_tokens"})
        self.assertEqual(result["usage"]["input_tokens"], 11)
        self.assertEqual(result["usage"]["output_tokens"], 7)
        self.assertEqual(result["usage"]["total_tokens"], 18)


if __name__ == "__main__":
    unittest.main()
