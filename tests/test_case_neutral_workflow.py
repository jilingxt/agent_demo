import json

from case_agent_demo.agents import ReportImageAgent, TextAgent, _facts_from_json
from case_agent_demo.case_replay import replay_case
from case_agent_demo.evidence_reasoning import AssertionNormalizer
from case_agent_demo.models import EvidenceNode, Material, MaterialType
from case_agent_demo.prompt_config import PromptLoader
from case_agent_demo.workflow import CaseWorkflow


def test_workflow_runs_without_manually_confirmed_case_type():
    result = CaseWorkflow.demo().run(
        [
            Material(
                "S-1",
                MaterialType.STATEMENT,
                "报警人王小明称李大海虚构投资项目，王小明信以为真后转账十万元。",
            )
        ]
    )

    assert result.confirmed_case_type == ""
    assert result.case_type_context.status == "provisional"
    assert "deception_disposition" in result.inferred_case_domains
    assert result.evidence_book is not None
    assert result.evidence_book.allegations
    assert result.case_graph.claims
    assert (result.bayesian_result or {}).get("selected_model_ids") == [
        "deception_disposition"
    ]
    assert any(item.article == "第二百六十六条" for item in result.legal_matches)


def test_legacy_confirmed_case_type_remains_a_compatible_override():
    result = CaseWorkflow.demo().run(
        [Material("S-1", MaterialType.STATEMENT, "张三称20时在家。")],
        confirmed_case_type="人工测试类型",
    )

    assert result.confirmed_case_type == "人工测试类型"
    assert result.case_type_context.status == "confirmed"
    assert result.case_type_context.source == "legacy_api"


def test_strict_legacy_mode_can_still_require_human_confirmation():
    workflow = CaseWorkflow.demo()

    try:
        workflow.run(
            [Material("S-1", MaterialType.STATEMENT, "张三称20时在家。")],
            require_human_confirmation=True,
        )
    except Exception as exc:
        assert exc.__class__.__name__ == "HumanConfirmationRequired"
    else:
        raise AssertionError("strict legacy mode must preserve the confirmation gate")


def test_structured_text_output_preserves_case_neutral_assertion_fields():
    material = Material("S-1", MaterialType.STATEMENT, "报警人陈某报称周某实施相关行为。")

    facts = _facts_from_json(
        {
            "facts": [
                {
                    "person": "陈某",
                    "behavior": "周某实施相关行为",
                    "actor": "周某",
                    "target_person": "陈某",
                    "predicate": "unmodeled_conduct",
                    "event_id": "EVENT-1",
                    "stance": "affirm",
                    "assertion_role": "allegation",
                    "declarant": "陈某",
                    "declarant_role": "reporting_person",
                    "evidence_category": "statement",
                }
            ]
        },
        material,
    )

    assert facts[0].metadata["assertion_role"] == "allegation"
    assert facts[0].metadata["declarant_role"] == "reporting_person"
    assert facts[0].metadata["evidence_category"] == "statement"


def test_witness_statement_is_evidence_but_not_an_allegation_anchor():
    node = EvidenceNode(
        node_id="N-WITNESS",
        node_type="fact",
        source_material_id="S-WITNESS",
        source_type="statement",
        summary="证人陈某称看到周某实施相关行为",
        person="陈某",
        metadata={
            "declarant": "陈某",
            "declarant_role": "witness",
            "actor": "周某",
            "predicate": "unmodeled_conduct",
            "stance": "affirm",
        },
    )

    assertion = AssertionNormalizer().normalize_node(node)

    assert assertion.assertion_role == "statement_evidence"


def test_unknown_predicates_keep_different_targets_in_different_claims():
    nodes = [
        EvidenceNode(
            node_id=f"N-{target}",
            node_type="fact",
            source_material_id=f"S-{target}",
            source_type="statement",
            summary=f"周某对{target}实施尚未建模的行为",
            metadata={
                "declarant": target,
                "declarant_role": "reporting_person",
                "actor": "周某",
                "target_person": target,
                "predicate": "unmodeled_conduct",
                "stance": "affirm",
            },
        )
        for target in ("陈某", "王某")
    ]
    normalizer = AssertionNormalizer()

    claims = normalizer.build_claims(normalizer.normalize_graph(type("G", (), {"nodes": nodes})()))

    assert {claim.target_person for claim in claims} == {"陈某", "王某"}


def test_case_replay_does_not_require_case_type(tmp_path):
    case_dir = tmp_path / "open_case"
    statements = case_dir / "statements"
    statements.mkdir(parents=True)
    (statements / "报警人笔录.txt").write_text(
        "报警人陈某称周某虚构项目，陈某信以为真后转账一万元。",
        encoding="utf-8",
    )
    (case_dir / "case.json").write_text(
        json.dumps(
            {
                "case_id": "OPEN-1",
                "materials": [
                    {
                        "material_id": "S-REPORTER",
                        "material_type": "statement",
                        "path": "statements/报警人笔录.txt",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = replay_case(case_dir, CaseWorkflow.demo())

    assert result.confirmed_case_type == ""
    assert result.evidence_book is not None
    assert result.evidence_book.allegations


def test_text_fallback_propagates_explicit_source_role():
    fact = TextAgent().extract(
        Material(
            "S-WITNESS",
            MaterialType.STATEMENT,
            "证人王某称看见周某实施相关行为。",
            metadata={"declarant_role": "witness"},
        )
    )[0]

    assert fact.metadata["declarant_role"] == "witness"
    assert fact.metadata["assertion_role"] == "statement_evidence"


def test_llm_prompts_use_the_same_case_neutral_assertion_contract():
    text_prompt = PromptLoader().load("text_agent")
    reasoning_prompt = PromptLoader().load("reasoning_agent")

    for field in (
        "declarant",
        "declarant_role",
        "actor",
        "target_person",
        "predicate",
        "stance",
        "assertion_role",
        "event_id",
        "evidence_category",
    ):
        assert f'"{field}"' in text_prompt
    assert "不得先判断案件类型" in text_prompt
    assert "人工确认案件类型" not in reasoning_prompt


def test_alleged_actor_denial_becomes_opposing_statement_evidence():
    fact = TextAgent().extract(
        Material(
            "S-ACTOR",
            MaterialType.STATEMENT,
            "行为人李大海称项目真实，并未欺骗王小明。",
            metadata={"declarant_role": "alleged_actor"},
        )
    )[0]
    assertion = fact.metadata["assertions"][0]

    assert assertion["predicate"] == "deceptive_representation"
    assert assertion["stance"] == "deny"
    assert assertion["assertion_role"] == "defense_response"


def test_report_time_reference_does_not_create_a_new_disposition_actor():
    fact = ReportImageAgent().extract(
        Material(
            "R-PROJECT",
            MaterialType.REPORT_IMAGE,
            "登记记录显示李大海向王小明声称存在的项目在转账时并不存在，"
            "该陈述与登记记录不符。",
        )
    )[0]

    predicates = {item["predicate"] for item in fact.metadata["assertions"]}

    assert "deceptive_representation" in predicates
    assert "property_disposition" not in predicates


def test_group_actor_before_location_is_not_replaced_by_location_fragment():
    fact = TextAgent().extract(
        Material(
            "S-WITNESS",
            MaterialType.STATEMENT,
            "证人证言。被询问人陈凯。周强等多人在车站大厅反复起哄、冲闯，扰乱秩序。",
            metadata={"declarant_role": "witness"},
        )
    )[0]

    assert {item["actor"] for item in fact.metadata["assertions"]} == {"周强"}
