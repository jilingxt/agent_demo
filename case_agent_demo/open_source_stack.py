from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpenSourceComponent:
    name: str
    repository: str
    local_path: str
    role: str
    adoption: str
    installed: bool = False
    executed: bool = False


@dataclass(frozen=True)
class OpenSourceStack:
    components: tuple[OpenSourceComponent, ...]

    @classmethod
    def default(cls) -> "OpenSourceStack":
        root = Path(__file__).resolve().parents[1]
        external = root / "external"
        return cls(
            components=(
                OpenSourceComponent(
                    name="langgraph",
                    repository="https://github.com/langchain-ai/langgraph",
                    local_path=str(external / "langgraph"),
                    role="workflow_orchestration",
                    adoption="Use as the target orchestration layer for stateful case workflow and human gates.",
                ),
                OpenSourceComponent(
                    name="llama_index",
                    repository="https://github.com/run-llama/llama_index",
                    local_path=str(external / "llama_index"),
                    role="rag_and_retrieval",
                    adoption="Use as the target retrieval layer for laws, regulations, citations, and source-bound RAG.",
                ),
                OpenSourceComponent(
                    name="docling",
                    repository="https://github.com/docling-project/docling",
                    local_path=str(external / "docling"),
                    role="document_preprocessing_optional",
                    adoption="Use as a future document parsing reference for Word/PDF preprocessing.",
                ),
                OpenSourceComponent(
                    name="agent-wiz",
                    repository="https://github.com/Repello-AI/Agent-Wiz",
                    local_path=str(external / "agent-wiz"),
                    role="security_review",
                    adoption="Use for future static workflow visualization and threat modeling of agent/tool calls.",
                ),
            )
        )

    def component(self, name: str) -> OpenSourceComponent:
        for component in self.components:
            if component.name == name:
                return component
        raise KeyError(name)
