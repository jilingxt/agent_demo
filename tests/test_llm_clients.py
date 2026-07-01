import unittest
import urllib.error
from io import BytesIO
from unittest.mock import patch

from case_agent_demo.config import ModelProfile
from case_agent_demo.llm_clients import (
    ApiClientConfig,
    Dsv4Client,
    ModelApiError,
    QwenVisionClient,
)


class LlmClientTests(unittest.TestCase):
    def test_dsv4_payload_is_openai_compatible(self):
        client = Dsv4Client(ApiClientConfig("https://example.test/v1", "secret"))
        profile = ModelProfile("reasoning", "deepseek", "deepseek-v4-pro", 0.1, "high")

        payload = client.build_chat_payload(profile, "system prompt", "user input")

        self.assertEqual(payload["model"], "deepseek-v4-pro")
        self.assertEqual(payload["temperature"], 0.1)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")

    def test_qwen_payload_accepts_external_image_prompt(self):
        client = QwenVisionClient(ApiClientConfig("https://qwen.example.test/v1", "secret"))
        profile = ModelProfile("vision", "qwen", "qwen2.5-vl-72b-instruct", 0.0, "vision", "image_url")

        payload = client.build_vision_payload(profile, "描述这张证据图片", "https://example.test/image.jpg")

        self.assertEqual(payload["model"], "qwen2.5-vl-72b-instruct")
        self.assertEqual(payload["temperature"], 0.0)
        content = payload["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")

    def test_http_error_includes_provider_response_without_leaking_key(self):
        client = QwenVisionClient(ApiClientConfig("https://dashscope.aliyuncs.com/compatible-mode/v1", "secret-key"))
        payload = {"model": "qwen2.5-vl-72b-instruct", "messages": []}
        error_body = b'{"error":{"code":"Forbidden","message":"Model access denied"}}'
        http_error = urllib.error.HTTPError(
            url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=BytesIO(error_body),
        )

        with patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(ModelApiError) as context:
                client.chat_completions(payload)

        message = str(context.exception)
        self.assertIn("HTTP 403 Forbidden", message)
        self.assertIn("Forbidden", message)
        self.assertIn("Model access denied", message)
        self.assertIn("config/api_keys.toml", message)
        self.assertNotIn("secret-key", message)


if __name__ == "__main__":
    unittest.main()
