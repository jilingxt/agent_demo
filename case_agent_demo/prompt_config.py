from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def default_prompt_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "prompts"


@dataclass(frozen=True)
class PromptLoader:
    prompt_dir: Path | str = default_prompt_dir()

    def load(self, name: str) -> str:
        path = Path(self.prompt_dir) / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
