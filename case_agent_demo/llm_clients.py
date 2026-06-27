from __future__ import annotations

import json
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from case_agent_demo.config import ModelProfile


class MissingApiKeyError(RuntimeError):
    """Raised when a required API key is absent from the API key config file."""


@dataclass(frozen=True)
class SecretValue:
    _value: str

    def get_secret_value(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretValue(********)"

    __str__ = __repr__


@dataclass(frozen=True)
class ApiClientConfig:
    base_url: str
    api_key: SecretValue | str
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if isinstance(self.api_key, str):
            object.__setattr__(self, "api_key", SecretValue(self.api_key))

    @classmethod
    def from_file(cls, provider: str, path: str | Path | None = None) -> "ApiClientConfig":
        provider = provider.lower()
        config_path = Path(path) if path is not None else default_api_keys_path()
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        section = data.get(provider, {})
        api_key = str(section.get("api_key", "")).strip()
        if not api_key:
            raise MissingApiKeyError(f"{provider}.api_key is required in {config_path}")
        base_url = str(section.get("base_url", "")).strip() or _default_base_url(provider)
        timeout = int(section.get("timeout_seconds", 120))
        return cls(base_url=base_url.rstrip("/"), api_key=api_key, timeout_seconds=timeout)

    def __repr__(self) -> str:
        return (
            f"ApiClientConfig(base_url={self.base_url!r}, "
            f"api_key={self.api_key!r}, timeout_seconds={self.timeout_seconds!r})"
        )


def default_api_keys_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "api_keys.toml"


def _default_base_url(provider: str) -> str:
    if provider == "deepseek":
        return "https://api.deepseek.com"
    if provider == "qwen":
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"
    return ""


class OpenAICompatibleClient:
    def __init__(self, config: ApiClientConfig) -> None:
        self.config = config

    def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class Dsv4Client(OpenAICompatibleClient):
    @classmethod
    def from_config_file(cls, path: str | Path | None = None) -> "Dsv4Client":
        return cls(ApiClientConfig.from_file("deepseek", path))

    def build_chat_payload(self, profile: ModelProfile, system_prompt: str, user_input: str) -> dict[str, Any]:
        return {
            "model": profile.model_name,
            "temperature": profile.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        }


class QwenVisionClient(OpenAICompatibleClient):
    @classmethod
    def from_config_file(cls, path: str | Path | None = None) -> "QwenVisionClient":
        return cls(ApiClientConfig.from_file("qwen", path))

    def build_vision_payload(self, profile: ModelProfile, prompt: str, image_url: str) -> dict[str, Any]:
        return {
            "model": profile.model_name,
            "temperature": profile.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }
