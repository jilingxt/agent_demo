from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path


DEEPSEEK_V4_PRO_MODEL = "deepseek-v4-pro"
DEEPSEEK_V4_FLASH_MODEL = "deepseek-v4-flash"
QWEN_25_VL_72B_INSTRUCT_MODEL = "qwen2.5-vl-72b-instruct"


@dataclass(frozen=True)
class ModelProfile:
    role: str
    provider: str
    model_name: str
    temperature: float = 0.0
    reasoning_level: str = "low"
    input_mode: str = "text"


@dataclass(frozen=True)
class ModelProfiles:
    planning: ModelProfile = field(
        default_factory=lambda: ModelProfile("planning", "deepseek", DEEPSEEK_V4_PRO_MODEL, 0.2, "high")
    )
    text: ModelProfile = field(
        default_factory=lambda: ModelProfile("text", "deepseek", DEEPSEEK_V4_FLASH_MODEL, 0.0, "low")
    )
    database: ModelProfile = field(
        default_factory=lambda: ModelProfile("database", "deepseek", DEEPSEEK_V4_FLASH_MODEL, 0.0, "low")
    )
    vision: ModelProfile = field(
        default_factory=lambda: ModelProfile(
            "vision",
            "qwen",
            QWEN_25_VL_72B_INSTRUCT_MODEL,
            0.0,
            "vision",
            "qwen_api_or_external_qwen_result",
        )
    )
    report_image: ModelProfile = field(
        default_factory=lambda: ModelProfile(
            "report_image",
            "qwen+deepseek",
            f"{QWEN_25_VL_72B_INSTRUCT_MODEL}+{DEEPSEEK_V4_PRO_MODEL}",
            0.1,
            "high",
            "external_qwen_result_then_text_reasoning",
        )
    )
    conflict: ModelProfile = field(
        default_factory=lambda: ModelProfile("conflict", "deepseek", DEEPSEEK_V4_PRO_MODEL, 0.0, "high")
    )
    rag: ModelProfile = field(
        default_factory=lambda: ModelProfile("rag", "deepseek", DEEPSEEK_V4_FLASH_MODEL, 0.0, "low")
    )
    reasoning: ModelProfile = field(
        default_factory=lambda: ModelProfile("reasoning", "deepseek", DEEPSEEK_V4_PRO_MODEL, 0.1, "high")
    )
    judge: ModelProfile = field(
        default_factory=lambda: ModelProfile("judge", "deepseek", DEEPSEEK_V4_PRO_MODEL, 0.0, "high")
    )
    review: ModelProfile = field(
        default_factory=lambda: ModelProfile("review", "deepseek", DEEPSEEK_V4_PRO_MODEL, 0.0, "high")
    )

    @classmethod
    def from_runtime_config(cls, path: str | Path | None = None) -> "ModelProfiles":
        profiles = cls()
        config_path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "config" / "api_keys.toml"
        if not config_path.exists():
            return profiles
        data = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
        qwen_model = str(data.get("qwen", {}).get("model_name", "")).strip()
        if not qwen_model:
            return profiles
        vision = replace(profiles.vision, model_name=qwen_model)
        report_image = replace(
            profiles.report_image,
            model_name=f"{qwen_model}+{DEEPSEEK_V4_PRO_MODEL}",
        )
        return replace(profiles, vision=vision, report_image=report_image)
