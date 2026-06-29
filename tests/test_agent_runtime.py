import json
import tempfile
import unittest
from pathlib import Path

from case_agent_demo.agent_runtime import AgentRuntime, AgentRuntimeConfigError
from case_agent_demo.config import ModelProfile
from case_agent_demo.prompt_config import PromptLoader


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.payloads = []

    def build_chat_payload(self, profile, system_prompt, user_input):
        payload = {
            "model": profile.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        }
        self.payloads.append(payload)
        return payload

    def chat_completions(self, payload):
        return {"choices": [{"message": {"content": self.content}}]}


class AgentRuntimeTests(unittest.TestCase):
    def test_run_json_uses_prompt_and_parser_when_client_returns_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp)
            (prompt_dir / "text_agent.md").write_text("system prompt", encoding="utf-8")
            client = FakeClient(json.dumps({"value": "ok"}))
            runtime = AgentRuntime(client=client, prompt_loader=PromptLoader(prompt_dir))
            profile = ModelProfile("text", "deepseek", "deepseek-v4-flash", 0.0, "low", "text")

            result = runtime.run_json(
                "text_agent",
                profile,
                "only this statement",
                fallback=lambda: {"value": "fallback"},
                parser=lambda data: data,
            )

            self.assertEqual(result, {"value": "ok"})
            self.assertEqual(client.payloads[0]["messages"][1]["content"], "only this statement")

    def test_run_json_falls_back_without_client_or_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp)
            (prompt_dir / "text_agent.md").write_text("system prompt", encoding="utf-8")
            profile = ModelProfile("text", "deepseek", "deepseek-v4-flash", 0.0, "low", "text")

            no_client = AgentRuntime(client=None, prompt_loader=PromptLoader(prompt_dir))
            self.assertEqual(
                no_client.run_json("text_agent", profile, "input", lambda: "fallback", lambda data: data),
                "fallback",
            )

            invalid_json = AgentRuntime(client=FakeClient("not json"), prompt_loader=PromptLoader(prompt_dir))
            self.assertEqual(
                invalid_json.run_json("text_agent", profile, "input", lambda: "fallback", lambda data: data),
                "fallback",
            )

    def test_missing_prompt_is_configuration_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AgentRuntime(client=None, prompt_loader=PromptLoader(Path(tmp)))
            profile = ModelProfile("text", "deepseek", "deepseek-v4-flash", 0.0, "low", "text")

            with self.assertRaises(AgentRuntimeConfigError):
                runtime.run_json("missing_prompt", profile, "input", lambda: "fallback", lambda data: data)


if __name__ == "__main__":
    unittest.main()
