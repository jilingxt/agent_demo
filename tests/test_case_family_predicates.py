import pytest

from case_agent_demo.models import infer_claim_types, infer_predicate_stance


@pytest.mark.parametrize(
    "text",
    [
        "该手机原由李四保管并占有",
        "多人在车站持续起哄扰乱秩序",
        "存在摔倒等其他合理致伤原因",
        "鉴定已排除其他原因",
    ],
)
def test_raw_text_never_selects_a_case_predicate(text):
    assert infer_claim_types(text) == ["unresolved_observation"]


def test_raw_text_never_selects_a_stance():
    assert infer_predicate_stance("没有、未、否认都只是原文", "custom_event") == "ambiguous"
