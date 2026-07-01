from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from case_agent_demo.config import ModelProfile
from case_agent_demo.llm_clients import QwenVisionClient
from case_agent_demo.models import Material
from case_agent_demo.prompt_config import PromptLoader


DEFAULT_PIC_AGENT_PROMPT_NAME = "pic_agent_qwen"


@dataclass(frozen=True)
class ImageEvidenceDescription:
    pic: str
    text: str
    confidence: float = 0.0
    raw_response: str = ""
    min_confidence: float = 0.9

    @property
    def needs_human_input(self) -> bool:
        return self.confidence < self.min_confidence

    def to_material_content(self) -> str:
        flag = "；需要人工复核" if self.needs_human_input else ""
        return f"图片内容：{self.pic}；文字识别：{self.text}{flag}"


@dataclass
class QwenImageEvidenceTool:
    client: QwenVisionClient
    profile: ModelProfile
    prompt: str
    min_confidence: float = 0.9

    @classmethod
    def from_config_file(
        cls,
        profile: ModelProfile,
        api_config_path: str | Path | None = None,
        prompt_loader: PromptLoader | None = None,
        prompt_name: str = DEFAULT_PIC_AGENT_PROMPT_NAME,
    ) -> "QwenImageEvidenceTool":
        loader = prompt_loader or PromptLoader()
        return cls(
            client=QwenVisionClient.from_config_file(api_config_path),
            profile=profile,
            prompt=loader.load(prompt_name),
        )

    def describe(self, material: Material) -> ImageEvidenceDescription:
        image_ref = material.source_path.strip()
        if not image_ref:
            raise ValueError(f"Material {material.material_id} has no source_path for Qwen vision")
        image_url = image_ref if _is_remote_url(image_ref) or image_ref.startswith("data:") else local_image_to_data_url(image_ref)
        payload = self.client.build_vision_payload(self.profile, self.prompt, image_url)
        response = self.client.chat_completions(payload)
        return parse_qwen_image_description(response, min_confidence=self.min_confidence)

    def describe_group(self, group_id: str, image_paths: list[str]) -> ImageEvidenceDescription:
        if not image_paths:
            raise ValueError(f"Image group {group_id} has no image paths for Qwen vision")
        image_urls = [
            image_path if _is_remote_url(image_path) or image_path.startswith("data:") else local_image_to_data_url(image_path)
            for image_path in image_paths
        ]
        payload = self.client.build_vision_group_payload(self.profile, self.prompt, image_urls)
        response = self.client.chat_completions(payload)
        return parse_qwen_image_description(response, min_confidence=self.min_confidence)


def local_image_to_data_url(path: str | Path) -> str:
    image_path = Path(path)
    mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    if mime_type not in {"image/jpeg", "image/png"}:
        raise ValueError(f"Unsupported image file for Qwen vision: {image_path} ({mime_type})")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def parse_qwen_image_description(response: dict[str, Any], min_confidence: float = 0.9) -> ImageEvidenceDescription:
    content = _extract_message_content(response)
    try:
        data = json.loads(_strip_json_fence(content))
    except json.JSONDecodeError:
        return ImageEvidenceDescription(pic=content.strip(), text="", confidence=0.0, raw_response=content)
    return ImageEvidenceDescription(
        pic=str(data.get("pic", "")).strip(),
        text=str(data.get("text", "")).strip(),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        raw_response=content,
        min_confidence=min_confidence,
    )


def _extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
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


def _is_remote_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")
