from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from case_agent_demo.config import ModelProfile
from case_agent_demo.llm_clients import ModelApiError
from case_agent_demo.prompt_config import PromptLoader


T = TypeVar("T")


class AgentRuntimeConfigError(RuntimeError):
    """Raised when an agent runtime configuration is invalid."""


@dataclass
class AgentRuntime:
    client: Any | None = None
    prompt_loader: PromptLoader = PromptLoader()

    def run_json(
        self,
        prompt_name: str,
        profile: ModelProfile,
        user_input: str,
        fallback: Callable[[], T],
        parser: Callable[[dict[str, Any]], T],
    ) -> T:
        try:
            system_prompt = self.prompt_loader.load(prompt_name)
        except FileNotFoundError as exc:
            raise AgentRuntimeConfigError(f"Prompt file not found for {prompt_name}") from exc

        if self.client is None:
            return fallback()

        try:
            payload = self.client.build_chat_payload(profile, system_prompt, user_input)
            response = self.client.chat_completions(payload)
            content = _extract_message_content(response)
            data = json.loads(_strip_json_fence(content))
            return parser(data)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, ModelApiError):
            return fallback()


def _extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    return str(content)


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
