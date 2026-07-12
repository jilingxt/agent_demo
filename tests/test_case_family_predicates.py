import pytest

from case_agent_demo.models import infer_claim_types, infer_predicate_stance


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("该手机原由李四保管并占有", "prior_possession"),
        ("手机从李四处转移到张三控制", "possession_transfer"),
        ("涉案手机已被追回并查明去向", "property_trace"),
        ("张三称只是借用并非拿走", "alternative_explanation"),
        ("多人在车站持续起哄扰乱秩序", "persistence_or_group"),
        ("商场被迫停止营业，通行受到影响", "operational_impact"),
        ("行为发生在医院候诊大厅等公共场所", "public_context"),
        ("张三冲闯办公场所并扰乱秩序", "public_order_conduct"),
        ("现场发现爆炸物和易燃危险物质", "dangerous_object_or_condition"),
        ("危险状态危及不特定多数人", "exposure"),
        ("危险物质泄漏且未采取控制措施", "control_failure"),
        ("行为人实施纵火并引爆装置", "hazardous_conduct"),
        ("岗位职责记录载明安全管理义务", "duty_record_present"),
        ("资格证书和任职证明已经调取", "qualification_record_present"),
        ("经查询未发现许可证", "authorization_record_absent"),
        ("监控记录显示行为人实施相关行为", "conduct_recorded"),
        ("损坏结果导致设备无法使用", "damage_exists"),
        ("损伤形态与所述作用机制吻合", "mechanism_compatible"),
        ("行为发生后立即出现损伤，时间接近", "temporal_proximity"),
        ("存在摔倒等其他合理致伤原因", "alternative_cause"),
    ],
)
def test_case_family_predicate_fallbacks(text, expected):
    assert expected in infer_claim_types(text)


def test_fallback_emits_multiple_atomic_predicates_from_one_sentence():
    predicates = infer_claim_types("多人在公共场所持续起哄扰乱秩序，导致通行受到影响")

    assert {
        "persistence_or_group",
        "public_context",
        "public_order_conduct",
        "operational_impact",
    }.issubset(predicates)


def test_excluded_alternative_cause_is_negative_not_affirmative():
    text = "鉴定已排除自行摔倒等其他合理致伤原因，作用机制吻合"

    assert "alternative_cause" in infer_claim_types(text)
    assert infer_predicate_stance(text, "alternative_cause") == "deny"


def test_ambiguous_word_origin_does_not_imply_prior_possession():
    assert "prior_possession" not in infer_claim_types("事故原由仍需调查")
