from __future__ import annotations

import json
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from case_agent_demo.config import ModelProfile


class MissingApiKeyError(RuntimeError):
    """Raised when a required API key is absent from the API key config file."""


class ModelApiError(RuntimeError):
    """Raised when a configured model provider rejects or fails a request."""


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
        data = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
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
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ModelApiError(_format_http_error(url, exc)) from exc
        except urllib.error.URLError as exc:
            raise ModelApiError(
                f"LLM API request failed before receiving a response: {exc.reason}. "
                "Check config/api_keys.toml base_url, network/proxy settings, and provider availability."
            ) from exc


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

    def build_vision_group_payload(self, profile: ModelProfile, prompt: str, image_urls: list[str]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in image_urls)
        return {
            "model": profile.model_name,
            "temperature": profile.temperature,
            "messages": [{"role": "user", "content": content}],
        }


def _format_http_error(url: str, exc: urllib.error.HTTPError) -> str:
    body = _read_error_body(exc)
    hint = (
        "Check config/api_keys.toml: api_key, base_url, model name, workspace/region permissions, "
        "and whether the model is enabled for this account."
    )
    if "dashscope.aliyuncs.com" in url and exc.code in {401, 403}:
        hint += (
            " For Qwen/DashScope 401 or 403, verify that the key is a Model Studio/DashScope key, "
            "the account has access to the configured vision model, and the base_url matches the required workspace endpoint."
        )
    message = f"LLM API request failed: HTTP {exc.code} {exc.reason} for {url}. {hint}"
    if body:
        message += f" Provider response: {body}"
    return message


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
