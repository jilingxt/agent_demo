from __future__ import annotations

from dataclasses import dataclass, field

from case_agent_demo.agents import (
    ConflictAgent,
    EvidenceGraphAgent,
    JudgeAgent,
    PicAgent,
    PlanningAgent,
    ReasoningAgent,
    ReportImageAgent,
    ReviewAgent,
    TextAgent,
)
from case_agent_demo.config import ModelProfiles
from case_agent_demo.models import (
    CaseTypeSuggestion,
    Fact,
    Material,
    MaterialType,
    WorkflowResult,
)
from case_agent_demo.open_source_stack import OpenSourceStack
from case_agent_demo.tools import LegalRetrievalTool


class HumanConfirmationRequired(RuntimeError):
    """Raised when execution is attempted before human case-type confirmation."""


@dataclass
class CaseWorkflow:
    model_profiles: ModelProfiles = field(default_factory=ModelProfiles)
    open_source_stack: OpenSourceStack = field(default_factory=OpenSourceStack.default)
    planning_agent: PlanningAgent = field(default_factory=PlanningAgent)
    text_agent: TextAgent = field(default_factory=TextAgent)
    pic_agent: PicAgent = field(default_factory=PicAgent)
    report_image_agent: ReportImageAgent = field(default_factory=ReportImageAgent)
    evidence_graph_agent: EvidenceGraphAgent = field(default_factory=EvidenceGraphAgent)
    conflict_agent: ConflictAgent = field(default_factory=ConflictAgent)
    legal_tool: LegalRetrievalTool = field(default_factory=LegalRetrievalTool)
    reasoning_agent: ReasoningAgent = field(default_factory=ReasoningAgent)
    judge_agent: JudgeAgent = field(default_factory=JudgeAgent)
    review_agent: ReviewAgent = field(default_factory=ReviewAgent)

    def __post_init__(self) -> None:
        self.report_image_agent.legal_tool = self.legal_tool
        self.evidence_graph_agent.legal_tool = self.legal_tool
        self.reasoning_agent.legal_tool = self.legal_tool
        self.judge_agent.legal_tool = self.legal_tool
        self.review_agent.legal_tool = self.legal_tool

    @classmethod
    def demo(cls) -> "CaseWorkflow":
        return cls()

    def suggest_case_type(self, materials: list[Material]) -> CaseTypeSuggestion:
        return self.planning_agent.suggest(materials)

    def run(self, materials: list[Material], confirmed_case_type: str | None = None) -> WorkflowResult:
        if not confirmed_case_type:
            raise HumanConfirmationRequired("人工确认案件定性后，才能开始 agent 规划和执行。")

        facts: list[Fact] = []
        executed_agents = ["planning_agent"]
        for material in materials:
            if material.material_type == MaterialType.STATEMENT:
                facts.extend(self.text_agent.runnable.invoke(material))
                executed_agents.append("text_agent")
            elif material.material_type == MaterialType.EVIDENCE_IMAGE:
                facts.extend(self.pic_agent.runnable.invoke(material))
                executed_agents.append("pic_agent")
            elif material.material_type == MaterialType.REPORT_IMAGE:
                facts.extend(self.report_image_agent.runnable.invoke(material))
                executed_agents.append("report_image_agent")

        case_graph = self.evidence_graph_agent.build(facts)
        executed_agents.append("case_graph_agent")

        conflicts = self.conflict_agent.runnable.invoke(case_graph)
        executed_agents.append("conflict_agent")

        legal_matches = self.reasoning_agent.retrieve_legal_matches(
            {"confirmed_case_type": confirmed_case_type, "evidence_graph": case_graph}
        )
        executed_agents.append("legal_retrieval_tool")

        draft_report = self.reasoning_agent.runnable.invoke(
            {
                "confirmed_case_type": confirmed_case_type,
                "evidence_graph": case_graph,
                "legal_matches": legal_matches,
                "conflicts": conflicts,
            }
        )
        executed_agents.append("reasoning_agent")

        challenges = self.judge_agent.runnable.invoke(
            {
                "case_graph": case_graph,
                "conflicts": conflicts,
                "legal_matches": legal_matches,
                "draft_report": draft_report,
            }
        )
        executed_agents.append("judge_agent")

        final_report = self.reasoning_agent.revise(draft_report, challenges)
        executed_agents.append("reasoning_agent_revision")

        review = self.review_agent.runnable.invoke(
            {
                "report": final_report,
                "supporting_fact_ids": [fact.fact_id for fact in case_graph.facts],
                "supporting_law_ids": [law.law_id for law in legal_matches],
                "challenges": challenges,
            }
        )
        executed_agents.append("review_agent")

        return WorkflowResult(
            confirmed_case_type=confirmed_case_type,
            executed_agents=executed_agents,
            case_graph=case_graph,
            legal_matches=legal_matches,
            conflicts=conflicts,
            challenges=challenges,
            draft_report=draft_report,
            final_report=final_report,
            report=final_report,
            review=review,
            evidence_graph=case_graph,
        )
