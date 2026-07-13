from __future__ import annotations

from collections.abc import Mapping, Sequence
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
from case_agent_demo.confidence import ClaimBuilder, ConfidenceEngine
from case_agent_demo.config import ModelProfiles
from case_agent_demo.evidence_reasoning_engine import EvidenceReasoningEngine
from case_agent_demo.evidence_book import EvidenceBookBuilder
from case_agent_demo.final_conflict_agent import FinalConflictAgent, issues_to_challenges
from case_agent_demo.graph_store import GraphStoreTool
from case_agent_demo.legal_kb import LegalKnowledgeBaseTool
from case_agent_demo.models import (
    CaseGraph,
    CaseTypeContext,
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
    legal_kb: LegalKnowledgeBaseTool = field(default_factory=LegalKnowledgeBaseTool)
    claim_builder: ClaimBuilder = field(default_factory=ClaimBuilder)
    confidence_engine: ConfidenceEngine = field(default_factory=ConfidenceEngine)
    evidence_reasoning_engine: EvidenceReasoningEngine = field(default_factory=EvidenceReasoningEngine)
    evidence_book_builder: EvidenceBookBuilder = field(default_factory=EvidenceBookBuilder)
    final_conflict_agent: FinalConflictAgent = field(default_factory=FinalConflictAgent)
    reasoning_agent: ReasoningAgent = field(default_factory=ReasoningAgent)
    judge_agent: JudgeAgent = field(default_factory=JudgeAgent)
    review_agent: ReviewAgent = field(default_factory=ReviewAgent)

    def __post_init__(self) -> None:
        self.legal_tool.legal_kb = self.legal_kb
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

    def run(
        self,
        materials: list[Material],
        confirmed_case_type: str | None = None,
        authority_verifications: Sequence[Mapping] | Mapping[str, Mapping] | None = None,
        require_human_confirmation: bool = False,
    ) -> WorkflowResult:
        if require_human_confirmation and not confirmed_case_type:
            raise HumanConfirmationRequired("人工确认案件定性后，才能开始 agent 规划和执行。")
        case_type_hint = (confirmed_case_type or "").strip()

        material_plan = self.planning_agent.plan_materials(materials)
        graph_store = GraphStoreTool()
        facts: list[Fact] = []
        executed_agents = ["planning_agent", "planning_agent_material_plan"]
        materials_by_id = {material.material_id: material for material in materials}
        processed_image_ids: set[str] = set()

        def ingest_facts(new_facts: list[Fact]) -> None:
            facts.extend(new_facts)
            for fact in new_facts:
                self.evidence_graph_agent.add_fact(graph_store, fact)

        for material in materials:
            if material.material_type == MaterialType.STATEMENT:
                ingest_facts(self.text_agent.runnable.invoke(material))
                executed_agents.append("text_agent")

        for task in material_plan.evidence_image_tasks:
            if self.pic_agent.vision_tool is not None and _task_has_source_paths(task):
                ingest_facts(self.pic_agent.extract_group(task.group_id, task.source_paths))
                processed_image_ids.update(task.material_ids)
                executed_agents.append("pic_agent_group")

        for task in material_plan.report_image_tasks:
            if self.report_image_agent.vision_tool is not None and _task_has_source_paths(task):
                ingest_facts(self.report_image_agent.extract_group(task.group_id, task.source_paths))
                processed_image_ids.update(task.material_ids)
                executed_agents.append("report_image_agent_group")

        for material in materials:
            if material.material_id in processed_image_ids:
                continue
            if material.material_type == MaterialType.EVIDENCE_IMAGE:
                ingest_facts(self.pic_agent.runnable.invoke(material))
                executed_agents.append("pic_agent")
            elif material.material_type == MaterialType.REPORT_IMAGE:
                ingest_facts(self.report_image_agent.runnable.invoke(material))
                executed_agents.append("report_image_agent")

        raw_graph = graph_store.to_graph()
        reasoning_result = self.evidence_reasoning_engine.evaluate(
            case_type=case_type_hint,
            evidence_graph=raw_graph,
            authority_verifications=authority_verifications,
        )
        case_graph = CaseGraph(
            nodes=raw_graph.nodes,
            edges=raw_graph.edges,
            claims=reasoning_result.claims,
        )
        executed_agents.extend(["case_graph_agent", "evidence_reasoning_engine"])

        conflicts = self.conflict_agent.runnable.invoke(case_graph)
        executed_agents.append("conflict_agent")

        allegation_rag_result = self.legal_tool.retrieve_result(
            {
                "confirmed_case_type": case_type_hint,
                "evidence_graph": case_graph,
                "assertions": reasoning_result.assertions,
                "purpose": "allegation_discovery",
            }
        )
        executed_agents.append("legal_candidate_discovery")

        legal_matches = self.reasoning_agent.retrieve_legal_matches(
            {
                "confirmed_case_type": case_type_hint,
                "evidence_graph": case_graph,
                "claim_assessments": reasoning_result.claim_assessments,
            }
        )
        executed_agents.append("legal_retrieval_tool")

        inferred_domains = list(reasoning_result.reasoning_trace.get("case_domains", []))
        case_type_context = CaseTypeContext(
            value=case_type_hint,
            status=(
                "confirmed"
                if case_type_hint
                else ("provisional" if inferred_domains else "unknown")
            ),
            source="legacy_api" if case_type_hint else "automatic",
            candidates=[
                f"{item.law_name}{item.article}"
                for item in allegation_rag_result.matches[:5]
            ],
            domains=inferred_domains,
        )
        evidence_book = self.evidence_book_builder.build(
            case_graph,
            reasoning_result.assertions,
            reasoning_result.claim_assessments,
            legal_matches=_unique_legal_matches(
                [*allegation_rag_result.matches, *legal_matches]
            ),
            legal_purpose="candidate_discovery",
            bayesian_result=reasoning_result.bayesian_result,
        )

        draft_report = self.reasoning_agent.runnable.invoke(
            {
                "confirmed_case_type": case_type_hint,
                "case_type_context": case_type_context,
                "evidence_graph": case_graph,
                "evidence_book": evidence_book,
                "legal_matches": legal_matches,
                "conflicts": conflicts,
                "claim_assessments": reasoning_result.claim_assessments,
                "bayesian_result": reasoning_result.bayesian_result,
            }
        )
        executed_agents.append("reasoning_agent")

        challenges = self.judge_agent.runnable.invoke(
            {
                "case_graph": case_graph,
                "conflicts": conflicts,
                "claim_assessments": reasoning_result.claim_assessments,
                "bayesian_result": reasoning_result.bayesian_result,
                "legal_matches": legal_matches,
                "draft_report": draft_report,
            }
        )
        executed_agents.append("judge_agent")
        legal_rag_result = self.legal_tool.retrieve_result(
            {
                "confirmed_case_type": case_type_hint,
                "evidence_graph": case_graph,
                "claim_assessments": reasoning_result.claim_assessments,
                "draft_report": draft_report,
                "purpose": "final_compliance_review",
            }
        )
        validation_issues = self.final_conflict_agent.review(
            case_type_hint,
            case_graph,
            draft_report,
            legal_rag_result,
            claim_assessments=reasoning_result.claim_assessments,
            bayesian_result=reasoning_result.bayesian_result,
        )
        challenges = [*challenges, *issues_to_challenges(validation_issues)]
        executed_agents.append("final_conflict_agent")

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
            confirmed_case_type=case_type_hint,
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
            material_plan=material_plan,
            validation_issues=validation_issues,
            assertions=reasoning_result.assertions,
            claim_assessments=reasoning_result.claim_assessments,
            bayesian_result=reasoning_result.bayesian_result,
            reasoning_trace=reasoning_result.reasoning_trace,
            model_versions=reasoning_result.model_versions,
            case_type_context=case_type_context,
            evidence_book=evidence_book,
            inferred_case_domains=inferred_domains,
        )


def _task_has_source_paths(task: object) -> bool:
    source_paths = getattr(task, "source_paths", [])
    return bool(source_paths) and all(str(path).strip() for path in source_paths)


def _unique_legal_matches(matches):
    result = []
    seen = set()
    for item in matches:
        key = (item.law_name, item.article)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
