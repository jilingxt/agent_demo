import tempfile
import unittest
from pathlib import Path

from case_agent_demo.config import ModelProfiles
from case_agent_demo.llm_clients import ApiClientConfig, Dsv4Client, MissingApiKeyError, QwenVisionClient
from case_agent_demo.prompt_config import PromptLoader


class RuntimeConfigTests(unittest.TestCase):
    def test_api_client_config_reads_api_key_from_toml_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "api_keys.toml"
            config_path.write_text(
                """
[deepseek]
api_key = "deepseek-secret"
base_url = "https://api.deepseek.com"
timeout_seconds = 90

[qwen]
api_key = "qwen-secret"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
timeout_seconds = 120
""".strip(),
                encoding="utf-8",
            )

            config = ApiClientConfig.from_file("deepseek", config_path)

        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.api_key.get_secret_value(), "deepseek-secret")
        self.assertEqual(config.timeout_seconds, 90)
        self.assertNotIn("deepseek-secret", repr(config))

    def test_api_client_config_requires_key_in_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "api_keys.toml"
            config_path.write_text("[qwen]\nbase_url = 'https://example.test'\n", encoding="utf-8")

            with self.assertRaises(MissingApiKeyError):
                ApiClientConfig.from_file("qwen", config_path)

    def test_api_config_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "api_keys.toml"
            config_path.write_text('\ufeff[qwen]\napi_key = "qwen-secret"\nmodel_name = "qwen-vl-plus"\n', encoding="utf-8")

            config = ApiClientConfig.from_file("qwen", config_path)
            profiles = ModelProfiles.from_runtime_config(config_path)

        self.assertEqual(config.api_key.get_secret_value(), "qwen-secret")
        self.assertEqual(profiles.vision.model_name, "qwen-vl-plus")

    def test_clients_can_be_created_from_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "api_keys.toml"
            config_path.write_text(
                """
[deepseek]
api_key = "deepseek-secret"

[qwen]
api_key = "qwen-secret"
""".strip(),
                encoding="utf-8",
            )

            dsv4 = Dsv4Client.from_config_file(config_path)
            qwen = QwenVisionClient.from_config_file(config_path)

        self.assertEqual(dsv4.config.base_url, "https://api.deepseek.com")
        self.assertEqual(qwen.config.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")

    def test_model_profiles_can_override_qwen_model_from_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "api_keys.toml"
            config_path.write_text(
                """
[qwen]
api_key = "qwen-secret"
model_name = "qwen-vl-plus"
""".strip(),
                encoding="utf-8",
            )

            profiles = ModelProfiles.from_runtime_config(config_path)

        self.assertEqual(profiles.vision.model_name, "qwen-vl-plus")
        self.assertEqual(profiles.report_image.model_name, "qwen-vl-plus+deepseek-v4-pro")

    def test_prompt_loader_reads_prompt_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp) / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "pic_agent_qwen.md").write_text("只输出 JSON。", encoding="utf-8")

            loader = PromptLoader(prompt_dir)

            self.assertEqual(loader.load("pic_agent_qwen"), "只输出 JSON。")


if __name__ == "__main__":
    unittest.main()
