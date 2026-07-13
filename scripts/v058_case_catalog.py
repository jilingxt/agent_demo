from __future__ import annotations

from dataclasses import dataclass


SYNTHETIC_BANNER = "合成测试材料，仅用于系统验证，不对应真实人员、单位或案件"


@dataclass(frozen=True)
class ProvisionPool:
    law_key: str
    title: str
    metadata_key: str
    metadata_value: str


PROVISION_POOLS = (
    ProvisionPool(
        law_key="criminal_law",
        title="中华人民共和国刑法",
        metadata_key="part",
        metadata_value="第二编 分则",
    ),
    ProvisionPool(
        law_key="public_security_law",
        title="中华人民共和国治安管理处罚法",
        metadata_key="chapter",
        metadata_value="第三章 违反治安管理的行为和处罚",
    ),
)


# Corpus curation is intentionally explicit and isolated from runtime inference.
PROVISION_REJECTIONS = {
    ("criminal_law", "第三百八十三条"): "pure_penalty_provision",
}
