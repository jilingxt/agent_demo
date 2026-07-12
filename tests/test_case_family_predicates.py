import pytest

from case_agent_demo.models import infer_claim_type


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
        ("经营者依法负有安全管理义务", "duty_exists"),
        ("该人员具备特定从业资格", "qualified_actor"),
        ("未经许可且无证经营", "authorization_absent"),
        ("行为人擅自违规经营", "prohibited_conduct"),
        ("损坏结果导致设备无法使用", "damage_exists"),
        ("损伤形态与所述作用机制吻合", "mechanism_compatible"),
        ("行为发生后立即出现损伤，时间接近", "temporal_proximity"),
        ("存在摔倒等其他合理致伤原因", "alternative_cause"),
    ],
)
def test_case_family_predicate_fallbacks(text, expected):
    assert infer_claim_type(text) == expected
