import unittest

from case_agent_demo.config import ModelProfile
from case_agent_demo.llm_clients import (
    ApiClientConfig,
    Dsv4Client,
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


if __name__ == "__main__":
    unittest.main()
