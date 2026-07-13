from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(frozen=True)
class MaterialSpec:
    material_id: str
    material_type: str
    folder: str
    filename: str
    title: str
    role: str
    paragraphs: tuple[str, ...] = ()
    questions: tuple[tuple[str, str], ...] = ()
    assertions: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    short_name: str
    law_key: str
    law_title: str
    article: str
    complexity_type: str
    case_type_hint: str
    summary: str
    materials: tuple[MaterialSpec, ...]
    required_claims: tuple[dict[str, Any], ...]
    forbidden_claims: tuple[dict[str, Any], ...] = ()
    expected_bayesian_models: tuple[str, ...] = ()
    expected_abstention: bool = False
    required_legal_articles: tuple[str, ...] = ()
    required_issue_types: tuple[str, ...] = ()
    forbidden_final_conclusions: tuple[str, ...] = (
        "已构成犯罪",
        "已构成违法",
        "应当处罚",
        "应判处",
    )
    authority_verifications: tuple[dict[str, Any], ...] = ()


def _fact(
    *,
    actor: str,
    predicate: str,
    behavior: str,
    event_id: str,
    stance: str = "affirm",
    target_person: str = "",
    object_entity: str = "",
    declarant: str = "",
    declarant_role: str = "unknown",
    assertion_role: str = "statement_evidence",
    evidence_category: str = "statement",
    confidence: float = 0.86,
    source_group: str = "",
    origin_evidence: str = "",
    time: str = "",
    location: str = "测试地点",
) -> dict[str, Any]:
    return {
        "actor": actor,
        "target_person": target_person,
        "object": object_entity,
        "predicate": predicate,
        "stance": stance,
        "behavior": behavior,
        "event_id": event_id,
        "declarant": declarant,
        "declarant_role": declarant_role,
        "assertion_role": assertion_role,
        "evidence_category": evidence_category,
        "confidence": confidence,
        "source_group": source_group,
        "origin_evidence": origin_evidence,
        "time": time,
        "location": location,
        "evidence_span": behavior,
    }


def _statement(
    case_id: str,
    suffix: str,
    filename: str,
    title: str,
    role: str,
    questions: tuple[tuple[str, str], ...],
    assertions: tuple[dict[str, Any], ...],
) -> MaterialSpec:
    return MaterialSpec(
        material_id=f"M-{case_id}-{suffix}",
        material_type="statement",
        folder="statements",
        filename=filename,
        title=title,
        role=role,
        questions=questions,
        assertions=assertions,
    )


def _report(
    case_id: str,
    suffix: str,
    filename: str,
    title: str,
    paragraphs: tuple[str, ...],
    assertions: tuple[dict[str, Any], ...],
) -> MaterialSpec:
    return MaterialSpec(
        material_id=f"M-{case_id}-{suffix}",
        material_type="report_image",
        folder="reports",
        filename=filename,
        title=title,
        role="synthetic_report",
        paragraphs=paragraphs,
        assertions=assertions,
    )


def build_case_catalog() -> tuple[CaseSpec, ...]:
    return (
        _cr353(),
        _cr185(),
        _cr189(),
        _cr429(),
        _cr186(),
        _ps51(),
        _ps52(),
        _ps31(),
        _ps50(),
        _ps83(),
    )


def _cr353() -> CaseSpec:
    case_id = "CR-353"
    event = "EVT-CR-353-01"
    consumer = "测试人员乙"
    actor = "测试人员甲"
    return CaseSpec(
        case_id=case_id,
        short_name="引诱行为争议",
        law_key="criminal_law",
        law_title="中华人民共和国刑法",
        article="第三百五十三条",
        complexity_type="direct_denial",
        case_type_hint="涉管制物质行为线索",
        summary="摄入事实有客观材料支持，但谁实施引诱、是否存在明确引诱行为仍有直接冲突。",
        materials=(
            _statement(
                case_id,
                "S1",
                "相关人员乙笔录.docx",
                "相关人员询问笔录",
                "reporting_party",
                (
                    ("请说明当晚经过。", "我在测试场所与测试人员甲见面，之后摄入了编号为样本物A的物质。"),
                    ("是谁建议你摄入？", "测试人员甲多次说可以尝试，并把一个无标识小袋放到桌上。"),
                    ("你是否能确认物质来源？", "我只看到小袋在桌上，不能确认此前由谁保管。"),
                ),
                (
                    _fact(actor=actor, target_person=consumer, object_entity="样本物A", predicate="inducing_consumption", behavior="测试人员乙称测试人员甲多次劝其尝试样本物A", event_id=event, declarant=consumer, declarant_role="reporting_party", source_group="SG-CR353-S1", origin_evidence="OR-CR353-S1"),
                    _fact(actor=consumer, object_entity="样本物A", predicate="consumption_result", behavior="测试人员乙确认自己摄入样本物A", event_id=event, declarant=consumer, declarant_role="reporting_party", source_group="SG-CR353-S1", origin_evidence="OR-CR353-S1"),
                ),
            ),
            _statement(
                case_id,
                "S2",
                "测试人员甲笔录.docx",
                "被指认人员询问笔录",
                "alleged_actor",
                (
                    ("你是否劝测试人员乙摄入样本物A？", "没有。我明确没有作出劝说、引诱或强迫。"),
                    ("桌上小袋是谁放的？", "我到场时已经在那里，来源我不清楚。"),
                    ("你是否看见其摄入？", "我看见他拿起过小袋，但没有看清其后动作。"),
                ),
                (
                    _fact(actor=actor, target_person=consumer, object_entity="样本物A", predicate="inducing_consumption", behavior="测试人员甲直接否认实施劝说、引诱或强迫", event_id=event, stance="deny", declarant=actor, declarant_role="alleged_actor", source_group="SG-CR353-S2", origin_evidence="OR-CR353-S2"),
                ),
            ),
            _report(
                case_id,
                "R1",
                "电子数据研判报告.docx",
                "电子数据研判报告",
                (
                    "送检设备中提取到测试人员乙当晚发送的自述信息，内容可支持其已摄入样本物A。",
                    "现有聊天截图片段缺少完整账号认证和上下文，不能据此确认劝说信息的发送人为测试人员甲。",
                    "本报告仅描述数据内容及来源完整性，不对违法犯罪成立作出判断。",
                ),
                (
                    _fact(actor=consumer, object_entity="样本物A", predicate="consumption_result", behavior="电子数据记录支持测试人员乙当晚自述已摄入样本物A", event_id=event, declarant="测试记录人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.9, source_group="SG-CR353-R1", origin_evidence="OR-CR353-R1"),
                    _fact(actor=actor, target_person=consumer, predicate="actor_attribution", behavior="聊天片段无法确认相关劝说信息由测试人员甲发送", event_id=event, stance="ambiguous", declarant="测试记录人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.82, source_group="SG-CR353-R1", origin_evidence="OR-CR353-R1"),
                ),
            ),
        ),
        required_claims=(
            {"actor": actor, "predicate": "inducing_consumption", "target_person": consumer, "status": "contested"},
            {"actor": consumer, "predicate": "consumption_result", "object": "样本物A", "status": "supported"},
        ),
        expected_abstention=True,
        required_legal_articles=("第三百五十三条",),
        required_issue_types=("contested_but_not_refuted",),
    )


def _cr185() -> CaseSpec:
    case_id = "CR-185"
    event = "EVT-CR-185-01"
    actor = "测试职员甲"
    return CaseSpec(
        case_id=case_id,
        short_name="资金授权争议",
        law_key="criminal_law",
        law_title="中华人民共和国刑法",
        article="第一百八十五条",
        complexity_type="business_authorization_dispute",
        case_type_hint="机构资金使用争议",
        summary="资金划转和岗位权限有记录，但是否超越授权及是否属于挪用不能仅由流水推出。",
        materials=(
            _statement(case_id, "S1", "核查人员笔录.docx", "核查人员询问笔录", "reporting_party", (("发现了什么情况？", "测试账户A向测试账户B划转一笔测试资金，指令由测试职员甲发起。"), ("是否掌握授权文件？", "系统中有业务审批编号，但附件版本不完整。")), (
                _fact(actor=actor, object_entity="测试资金批次A", predicate="conduct_recorded", behavior="核查人员确认测试职员甲发起资金划转指令", event_id=event, declarant="测试核查人员", declarant_role="reporting_party", source_group="SG-CR185-S1", origin_evidence="OR-CR185-S1"),
                _fact(actor=actor, predicate="authorization_record_absent", behavior="现有审批附件不完整，授权范围尚不能确认", event_id=event, stance="ambiguous", declarant="测试核查人员", declarant_role="reporting_party", source_group="SG-CR185-S1", origin_evidence="OR-CR185-S1"),
            )),
            _statement(case_id, "S2", "测试职员甲笔录.docx", "相关职员询问笔录", "alleged_actor", (("是否发起该笔划转？", "是，我发起了系统指令。"), ("你是否没有授权？", "不是。该业务已通过测试审批流程，我按当日授权执行。"), ("资金是否供个人使用？", "没有，资金进入测试项目账户。")), (
                _fact(actor=actor, object_entity="测试资金批次A", predicate="conduct_recorded", behavior="测试职员甲承认发起资金划转指令", event_id=event, declarant=actor, declarant_role="alleged_actor", source_group="SG-CR185-S2", origin_evidence="OR-CR185-S2"),
                _fact(actor=actor, predicate="authorization_record_absent", behavior="测试职员甲否认无授权并称存在业务审批", event_id=event, stance="deny", declarant=actor, declarant_role="alleged_actor", source_group="SG-CR185-S2", origin_evidence="OR-CR185-S2"),
            )),
            _report(case_id, "R1", "资金流水核查报告.docx", "资金流水核查报告", ("测试账户A向测试账户B发生一次资金划转，金额使用区间值表示。", "操作日志对应测试职员甲的业务账号，但授权附件缺少最终签批页。", "资金后续进入测试项目账户，未发现直接进入个人账户的记录。"), (
                _fact(actor=actor, object_entity="测试资金批次A", predicate="conduct_recorded", behavior="系统日志记录测试职员甲业务账号发起资金划转", event_id=event, declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.92, source_group="SG-CR185-R1", origin_evidence="OR-CR185-R1"),
                _fact(actor=actor, predicate="duty_record_present", behavior="岗位记录显示测试职员甲具有业务指令职责", event_id=event, declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.88, source_group="SG-CR185-R1", origin_evidence="OR-CR185-R1"),
                _fact(actor=actor, predicate="authorization_record_absent", behavior="授权附件缺少最终签批页，授权范围待核", event_id=event, stance="ambiguous", declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-CR185-R1", origin_evidence="OR-CR185-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "conduct_recorded", "object": "测试资金批次A", "status": "supported"},
            {"actor": actor, "predicate": "authorization_record_absent", "status": "insufficient"},
        ),
        expected_bayesian_models=("status_duty",),
        required_legal_articles=("第一百八十五条",),
        required_issue_types=("insufficient_evidence",),
    )


def _cr189() -> CaseSpec:
    case_id = "CR-189"
    event = "EVT-CR-189-01"
    actor = "测试职员乙"
    return CaseSpec(
        case_id=case_id,
        short_name="票据证据不足",
        law_key="criminal_law",
        law_title="中华人民共和国刑法",
        article="第一百八十九条",
        complexity_type="evidence_insufficient",
        case_type_hint="票据业务核查",
        summary="经办行为可以确认，但规则违反、个人责任、因果关系和重大损失均缺少充分材料。",
        materials=(
            _statement(case_id, "S1", "业务主管笔录.docx", "业务主管询问笔录", "reporting_party", (("测试职员乙是否经办票据？", "其在系统中完成过形式审查。"), ("是否违规承兑或付款？", "目前只有流程截图，我不能确认其越权或明知材料不实。")), (
                _fact(actor=actor, object_entity="测试票据A", predicate="conduct_recorded", behavior="业务主管确认测试职员乙经办测试票据A的形式审查", event_id=event, declarant="测试主管甲", declarant_role="reporting_party", source_group="SG-CR189-S1", origin_evidence="OR-CR189-S1"),
                _fact(actor=actor, object_entity="测试票据A", predicate="authorization_record_absent", behavior="业务主管不能确认测试职员乙存在越权", event_id=event, stance="ambiguous", declarant="测试主管甲", declarant_role="reporting_party", source_group="SG-CR189-S1", origin_evidence="OR-CR189-S1"),
            )),
            _statement(case_id, "S2", "测试职员乙笔录.docx", "经办人员询问笔录", "alleged_actor", (("你做了哪些操作？", "我只完成形式审查并提交复核，没有决定承兑或付款。"), ("是否知道材料存在问题？", "当时没有发现异常，后续问题我不清楚。")), (
                _fact(actor=actor, object_entity="测试票据A", predicate="conduct_recorded", behavior="测试职员乙承认完成测试票据A的形式审查", event_id=event, declarant=actor, declarant_role="alleged_actor", source_group="SG-CR189-S2", origin_evidence="OR-CR189-S2"),
            )),
            _report(case_id, "R1", "票据业务核查报告.docx", "票据业务核查报告", ("系统日志显示测试职员乙完成形式审查，后续复核账号另有其人。", "现有材料未提供完整内部规则版本和授权矩阵。", "损失统计仅为初步估算，尚未完成回款、担保和责任原因核对。"), (
                _fact(actor=actor, object_entity="测试票据A", predicate="conduct_recorded", behavior="系统日志确认测试职员乙完成形式审查", event_id=event, declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.92, source_group="SG-CR189-R1", origin_evidence="OR-CR189-R1"),
                _fact(actor=actor, predicate="duty_record_present", behavior="岗位记录显示测试职员乙负有形式审查职责", event_id=event, declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-CR189-R1", origin_evidence="OR-CR189-R1"),
                _fact(actor=actor, object_entity="初步损失估算", predicate="result_exists", behavior="损失金额和责任原因尚未完成核对", event_id=event, stance="ambiguous", declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-CR189-R1", origin_evidence="OR-CR189-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "conduct_recorded", "object": "测试票据A", "status": "supported"},
            {"actor": actor, "predicate": "result_exists", "object": "初步损失估算", "status": "insufficient"},
        ),
        expected_bayesian_models=("status_duty",),
        required_legal_articles=("第一百八十九条",),
        required_issue_types=("insufficient_evidence",),
    )


def _cr429() -> CaseSpec:
    case_id = "CR-429"
    event = "EVT-CR-429-01"
    actor = "测试队员甲"
    target = "测试队员乙"
    return CaseSpec(
        case_id=case_id,
        short_name="训练救助争议",
        law_key="criminal_law",
        law_title="中华人民共和国刑法",
        article="第四百二十九条",
        complexity_type="non_offense_context",
        case_type_hint="特定义务场景核查",
        summary="事件发生于训练环境，且设备故障影响救助能力，不能把未完成救助直接等同于战场拒不救援。",
        materials=(
            _statement(case_id, "S1", "训练参与人员笔录.docx", "训练参与人员询问笔录", "reporting_party", (("当时发生了什么？", "测试队员乙在模拟区发出求助，测试队员甲没有进入封闭区域。"), ("现场是否属于实战？", "不是，是事先安排的训练。")), (
                _fact(actor=actor, target_person=target, predicate="non_rescue_conduct", behavior="训练参与人员称测试队员甲未进入模拟区实施救助", event_id=event, declarant="测试队员丙", declarant_role="witness", source_group="SG-CR429-S1", origin_evidence="OR-CR429-S1"),
                _fact(actor="训练组织方", predicate="battlefield_context", behavior="事件发生在事先安排的训练环境而非实战", event_id=event, stance="deny", declarant="测试队员丙", declarant_role="witness", source_group="SG-CR429-S1", origin_evidence="OR-CR429-S1"),
            )),
            _statement(case_id, "S2", "测试队员甲笔录.docx", "相关人员询问笔录", "alleged_actor", (("为何没有进入模拟区？", "入口锁止，备用装置也没有响应，我立即呼叫训练控制人员。"), ("你是否拒绝救助？", "没有，我当时无法安全进入。")), (
                _fact(actor=actor, target_person=target, predicate="rescue_capability", behavior="测试队员甲称因入口锁止而无法进入实施救助", event_id=event, stance="deny", declarant=actor, declarant_role="alleged_actor", source_group="SG-CR429-S2", origin_evidence="OR-CR429-S2"),
            )),
            _report(case_id, "R1", "训练设备核查报告.docx", "训练设备核查报告", ("训练计划、签到表和控制台记录均表明该活动为模拟训练。", "入口控制装置在求助时间段出现锁止故障，备用开关无有效响应。", "现有材料未记录重大损失，测试队员乙经现场处置后离开模拟区。"), (
                _fact(actor="训练组织方", predicate="battlefield_context", behavior="训练计划确认事件不是实战或战场环境", event_id=event, stance="deny", declarant="测试技术人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.95, source_group="SG-CR429-R1", origin_evidence="OR-CR429-R1"),
                _fact(actor=actor, target_person=target, predicate="rescue_capability", behavior="设备日志支持入口锁止并影响进入能力", event_id=event, stance="deny", declarant="测试技术人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.92, source_group="SG-CR429-R1", origin_evidence="OR-CR429-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "non_rescue_conduct", "target_person": target, "status": "supported"},
            {"actor": "训练组织方", "predicate": "battlefield_context", "status": "opposing_dominant"},
        ),
        expected_abstention=True,
        required_legal_articles=("第四百二十九条",),
        required_issue_types=("legal_element_missing",),
    )


def _cr186() -> CaseSpec:
    case_id = "CR-186"
    event = "EVT-CR-186-01"
    actor = "测试审批员甲"
    return CaseSpec(
        case_id=case_id,
        short_name="贷款部分承认",
        law_key="criminal_law",
        law_title="中华人民共和国刑法",
        article="第一百八十六条",
        complexity_type="partial_admission",
        case_type_hint="贷款审批规范核查",
        summary="审批行为被承认，但关联关系、违反规则、数额和损失需分别证明。",
        materials=(
            _statement(case_id, "S1", "业务复核人员笔录.docx", "业务复核人员询问笔录", "reporting_party", (("谁审批了测试贷款A？", "系统显示测试审批员甲完成了终审操作。"), ("借款方是否为关联方？", "档案里有同名信息，但主体对应关系尚未核实。")), (
                _fact(actor=actor, object_entity="测试贷款A", predicate="conduct_recorded", behavior="业务复核人员确认测试审批员甲完成终审操作", event_id=event, declarant="测试复核人员", declarant_role="reporting_party", source_group="SG-CR186-S1", origin_evidence="OR-CR186-S1"),
                _fact(actor=actor, object_entity="测试借款主体A", predicate="related_party_status", behavior="借款主体是否属于关联方尚未核实", event_id=event, stance="ambiguous", declarant="测试复核人员", declarant_role="reporting_party", source_group="SG-CR186-S1", origin_evidence="OR-CR186-S1"),
            )),
            _statement(case_id, "S2", "测试审批员甲笔录.docx", "审批人员询问笔录", "alleged_actor", (("是否完成终审？", "是，我完成了系统终审。"), ("你是否明知属于关联方？", "我不知道存在关联关系，系统当时没有提示。"), ("是否违反审批规则？", "我按当时展示的材料操作，是否缺件需要核对版本。")), (
                _fact(actor=actor, object_entity="测试贷款A", predicate="conduct_recorded", behavior="测试审批员甲承认完成系统终审", event_id=event, declarant=actor, declarant_role="alleged_actor", source_group="SG-CR186-S2", origin_evidence="OR-CR186-S2"),
                _fact(actor=actor, object_entity="测试借款主体A", predicate="related_party_status", behavior="测试审批员甲否认其明知借款主体属于关联方", event_id=event, stance="deny", declarant=actor, declarant_role="alleged_actor", source_group="SG-CR186-S2", origin_evidence="OR-CR186-S2"),
            )),
            _report(case_id, "R1", "贷款与资金核查报告.docx", "贷款与资金核查报告", ("系统日志确认测试审批员甲完成终审，岗位矩阵显示其负有审批职责。", "借款主体关联关系资料存在版本冲突，当前不能确认终审时已被正确披露。", "贷款余额、担保价值和实际损失仍在核对，不能用发放金额直接代替损失。"), (
                _fact(actor=actor, object_entity="测试贷款A", predicate="conduct_recorded", behavior="系统日志确认测试审批员甲完成终审", event_id=event, declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.94, source_group="SG-CR186-R1", origin_evidence="OR-CR186-R1"),
                _fact(actor=actor, predicate="duty_record_present", behavior="岗位矩阵显示测试审批员甲负有审批职责", event_id=event, declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.9, source_group="SG-CR186-R1", origin_evidence="OR-CR186-R1"),
                _fact(actor=actor, object_entity="测试借款主体A", predicate="related_party_status", behavior="关联关系资料存在版本冲突", event_id=event, stance="ambiguous", declarant="测试审计人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-CR186-R1", origin_evidence="OR-CR186-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "conduct_recorded", "object": "测试贷款A", "status": "supported"},
            {"actor": actor, "predicate": "related_party_status", "object": "测试借款主体A", "status": "insufficient"},
        ),
        expected_bayesian_models=("status_duty",),
        required_legal_articles=("第一百八十六条",),
        required_issue_types=("insufficient_evidence",),
    )


def _ps51() -> CaseSpec:
    case_id = "PS-51"
    event = "EVT-PS-51-01"
    actor = "测试人员丙"
    target = "测试人员丁"
    return CaseSpec(
        case_id=case_id,
        short_name="行为完整承认",
        law_key="public_security_law",
        law_title="中华人民共和国治安管理处罚法",
        article="第五十一条",
        complexity_type="full_admission",
        case_type_hint="人身行为线索",
        summary="行为人完整承认，另有独立目击和检查记录形成多源支持，但系统不自动决定违法或处罚。",
        materials=(
            _statement(case_id, "S1", "测试人员丁笔录.docx", "相关人员询问笔录", "reporting_party", (("请说明经过。", "测试人员丙与我争执后用手击打并推了我。"), ("现场有无其他人？", "测试见证人甲在旁边。")), (
                _fact(actor=actor, target_person=target, predicate="violence", behavior="测试人员丁称测试人员丙实施击打和推搡", event_id=event, declarant=target, declarant_role="reporting_party", source_group="SG-PS51-S1", origin_evidence="OR-PS51-S1"),
            )),
            _statement(case_id, "S2", "测试人员丙笔录.docx", "行为人询问笔录", "alleged_actor", (("你是否与测试人员丁发生身体冲突？", "是，我击打并推了他，我承认这些动作。"), ("是否有人在场？", "测试见证人甲在场。")), (
                _fact(actor=actor, target_person=target, predicate="violence", behavior="测试人员丙完整承认实施击打和推搡", event_id=event, declarant=actor, declarant_role="alleged_actor", source_group="SG-PS51-S2", origin_evidence="OR-PS51-S2"),
            )),
            _statement(case_id, "S3", "测试见证人甲笔录.docx", "见证人员询问笔录", "witness", (("你看见了什么？", "我直接看见测试人员丙击打并推了测试人员丁。"),), (
                _fact(actor=actor, target_person=target, predicate="violence", behavior="独立见证人直接看见测试人员丙实施击打和推搡", event_id=event, declarant="测试见证人甲", declarant_role="witness", source_group="SG-PS51-S3", origin_evidence="OR-PS51-S3"),
            )),
            _report(case_id, "R1", "现场检查报告.docx", "现场检查与就诊记录核查报告", ("检查记录显示测试人员丁存在表浅不适表现。", "记录形成时间与陈述事件接近，所述动作与表浅表现具有一般相容性。", "未发现能够单独解释该表现的其他已记录原因。"), (
                _fact(actor=target, predicate="injury_exists", behavior="检查记录显示测试人员丁存在表浅不适表现", event_id=event, declarant="测试检查人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.9, source_group="SG-PS51-R1", origin_evidence="OR-PS51-R1"),
                _fact(actor=actor, target_person=target, predicate="mechanism_consistency", behavior="所述动作与记录表现具有一般相容性", event_id=event, declarant="测试检查人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-PS51-R1", origin_evidence="OR-PS51-R1"),
                _fact(actor=actor, target_person=target, predicate="temporal_consistency", behavior="检查记录形成时间与陈述事件接近", event_id=event, declarant="测试检查人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-PS51-R1", origin_evidence="OR-PS51-R1"),
                _fact(actor=actor, target_person=target, predicate="alternative_cause", behavior="现有记录未发现其他明确原因", event_id=event, stance="deny", declarant="测试检查人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-PS51-R1", origin_evidence="OR-PS51-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "violence", "target_person": target, "status": "supported"},
            {"actor": target, "predicate": "injury_exists", "status": "supported"},
        ),
        expected_bayesian_models=("conduct_result",),
        required_legal_articles=("第五十一条",),
    )


def _ps52() -> CaseSpec:
    case_id = "PS-52"
    event = "EVT-PS-52-01"
    actor = "测试人员戊"
    target = "测试成年人己"
    return CaseSpec(
        case_id=case_id,
        short_name="行为与医疗解释",
        law_key="public_security_law",
        law_title="中华人民共和国治安管理处罚法",
        article="第五十二条",
        complexity_type="alternative_explanation",
        case_type_hint="公共场所行为争议",
        summary="目击印象和模糊影像不足以确认特定行为，另有可核查的突发医疗处置解释。",
        materials=(
            _statement(case_id, "S1", "测试成年人己笔录.docx", "相关人员询问笔录", "reporting_party", (("你为何报告该情况？", "我看到测试人员戊动作异常，感觉可能针对我，但当时距离较远。"), ("是否看清具体动作？", "没有完全看清，也没有身体接触。")), (
                _fact(actor=actor, target_person=target, predicate="indecent_conduct", behavior="测试成年人己认为远处异常动作可能针对自己但未看清", event_id=event, stance="ambiguous", declarant=target, declarant_role="reporting_party", source_group="SG-PS52-S1", origin_evidence="OR-PS52-S1"),
            )),
            _statement(case_id, "S2", "测试人员戊笔录.docx", "被指认人员询问笔录", "alleged_actor", (("你是否实施针对他人的不当行为？", "没有。我突发过敏不适，正在整理衣物并等待帮助。"), ("是否有就诊或求助记录？", "有测试服务台求助记录和随后形成的诊疗记录。")), (
                _fact(actor=actor, target_person=target, predicate="indecent_conduct", behavior="测试人员戊直接否认实施针对他人的不当行为", event_id=event, stance="deny", declarant=actor, declarant_role="alleged_actor", source_group="SG-PS52-S2", origin_evidence="OR-PS52-S2"),
                _fact(actor=actor, predicate="alternative_explanation", behavior="测试人员戊提出突发过敏不适的可核查解释", event_id=event, declarant=actor, declarant_role="alleged_actor", assertion_role="defense_response", source_group="SG-PS52-S2", origin_evidence="OR-PS52-S2"),
            )),
            _report(case_id, "R1", "影像与求助记录核查报告.docx", "影像与求助记录核查报告", ("影像分辨率不足，遮挡明显，不能识别具体动作指向。", "测试服务台记录显示同一时间测试人员戊请求医疗协助。", "后续测试诊疗记录与其所述突发不适时间相接近，但该记录仅支持医疗处置事实。"), (
                _fact(actor=actor, target_person=target, predicate="indecent_conduct", behavior="模糊影像不能识别测试人员戊是否实施特定动作", event_id=event, stance="ambiguous", declarant="测试数据人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.7, source_group="SG-PS52-R1", origin_evidence="OR-PS52-R1"),
                _fact(actor=actor, predicate="alternative_explanation", behavior="服务台和诊疗记录支持测试人员戊当时寻求医疗协助", event_id=event, declarant="测试数据人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.9, source_group="SG-PS52-R1", origin_evidence="OR-PS52-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "indecent_conduct", "target_person": target, "status": "opposing_dominant"},
            {"actor": actor, "predicate": "alternative_explanation", "status": "supported"},
        ),
        expected_abstention=True,
        required_legal_articles=("第五十二条",),
        required_issue_types=("opposing_evidence_dominant",),
    )


def _ps31() -> CaseSpec:
    case_id = "PS-31"
    event = "EVT-PS-31-01"
    actor = "测试组织者甲"
    return CaseSpec(
        case_id=case_id,
        short_name="普通活动纠纷",
        law_key="public_security_law",
        law_title="中华人民共和国治安管理处罚法",
        article="第三十一条",
        complexity_type="ordinary_activity_dispute",
        case_type_hint="社会活动边界核查",
        summary="私人场所的自愿交流活动与特定组织、强迫、欺骗、扰乱或伤害行为应当分开判断。",
        materials=(
            _statement(case_id, "S1", "活动参与者笔录.docx", "活动参与者询问笔录", "reporting_party", (("活动内容是什么？", "大家在预约的测试会议室自愿交流，没有要求交费或限制离开。"), ("是否有人受强迫或受损？", "我没有看到。争议来自场地方对活动主题不理解。")), (
                _fact(actor=actor, predicate="private_gathering", behavior="参与者称活动为预约场所内的自愿交流", event_id=event, declarant="测试参与者甲", declarant_role="witness", source_group="SG-PS31-S1", origin_evidence="OR-PS31-S1"),
                _fact(actor=actor, predicate="public_order_conduct", behavior="参与者未看到强迫、欺骗、扰乱或伤害行为", event_id=event, stance="deny", declarant="测试参与者甲", declarant_role="witness", source_group="SG-PS31-S1", origin_evidence="OR-PS31-S1"),
            )),
            _statement(case_id, "S2", "测试组织者甲笔录.docx", "活动组织者询问笔录", "alleged_actor", (("你组织了什么活动？", "我预约会议室进行普通交流，参加和离开均自愿。"), ("是否要求参与者服从或交付财物？", "没有。")), (
                _fact(actor=actor, predicate="private_gathering", behavior="测试组织者甲承认组织自愿交流活动", event_id=event, declarant=actor, declarant_role="alleged_actor", source_group="SG-PS31-S2", origin_evidence="OR-PS31-S2"),
                _fact(actor=actor, predicate="public_order_conduct", behavior="测试组织者甲否认存在强迫、欺骗或扰乱行为", event_id=event, stance="deny", declarant=actor, declarant_role="alleged_actor", source_group="SG-PS31-S2", origin_evidence="OR-PS31-S2"),
            )),
            _report(case_id, "R1", "场地与活动记录核查报告.docx", "场地与活动记录核查报告", ("场地预约、进出记录和现场照片显示活动在预约时间和房间内进行。", "记录中未见封堵出口、强迫交费、持续噪声或设施受损。", "该报告不能对活动内容作思想或价值评价。"), (
                _fact(actor=actor, predicate="public_context", behavior="活动位于预约的独立会议室而非开放公共区域", event_id=event, stance="deny", declarant="测试场地人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.9, source_group="SG-PS31-R1", origin_evidence="OR-PS31-R1"),
                _fact(actor=actor, predicate="operational_impact", behavior="现有记录未见场地运行受明显影响", event_id=event, stance="deny", declarant="测试场地人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", source_group="SG-PS31-R1", origin_evidence="OR-PS31-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "private_gathering", "status": "supported"},
            {"actor": actor, "predicate": "public_order_conduct", "status": "opposing_dominant"},
        ),
        expected_abstention=True,
        required_legal_articles=("第三十一条",),
        required_issue_types=("legal_element_missing",),
    )


def _ps50() -> CaseSpec:
    case_id = "PS-50"
    event = "EVT-PS-50-01"
    actor = "测试人员庚"
    target = "测试人员辛"
    return CaseSpec(
        case_id=case_id,
        short_name="账号归属争议",
        law_key="public_security_law",
        law_title="中华人民共和国治安管理处罚法",
        article="第五十条",
        complexity_type="actor_attribution_dispute",
        case_type_hint="电子通信行为核查",
        summary="信息内容客观存在，但账号标识、设备使用者和实际发送人是不同事实。",
        materials=(
            _statement(case_id, "S1", "测试人员辛笔录.docx", "信息接收人员询问笔录", "reporting_party", (("你收到了什么？", "测试账号A向我发送多条带有威胁含义的信息。"), ("为何认为是测试人员庚？", "账号昵称与他以前用过的相似，但我没看到发送过程。")), (
                _fact(actor="测试账号A", target_person=target, predicate="threatening_message", behavior="测试账号A向测试人员辛发送带有威胁含义的信息", event_id=event, declarant=target, declarant_role="reporting_party", source_group="SG-PS50-S1", origin_evidence="OR-PS50-S1"),
                _fact(actor=actor, predicate="sender_attribution", behavior="测试人员辛根据昵称推测测试人员庚为发送人", event_id=event, stance="ambiguous", declarant=target, declarant_role="reporting_party", source_group="SG-PS50-S1", origin_evidence="OR-PS50-S1"),
            )),
            _statement(case_id, "S2", "测试人员庚笔录.docx", "被指认人员询问笔录", "alleged_actor", (("测试账号A是否由你使用？", "不是，我没有注册或控制该账号。"), ("你是否发送过这些信息？", "没有。")), (
                _fact(actor=actor, predicate="sender_attribution", behavior="测试人员庚直接否认控制测试账号A或发送相关信息", event_id=event, stance="deny", declarant=actor, declarant_role="alleged_actor", source_group="SG-PS50-S2", origin_evidence="OR-PS50-S2"),
            )),
            _report(case_id, "R1", "电子数据核查报告.docx", "电子数据核查报告", ("接收设备中保存有测试账号A发送的信息，内容和时间戳可复核。", "平台回执仅能确认账号标识，现有导出材料不含实名验证、登录设备和网络来源。", "因此能够确认信息内容存在，不能确认测试人员庚为实际发送人。"), (
                _fact(actor="测试账号A", target_person=target, predicate="threatening_message", behavior="接收设备记录确认测试账号A发送的威胁信息存在", event_id=event, declarant="测试数据人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.95, source_group="SG-PS50-R1", origin_evidence="OR-PS50-R1"),
                _fact(actor=actor, predicate="sender_attribution", behavior="现有电子数据不能确认测试人员庚为实际发送人", event_id=event, stance="ambiguous", declarant="测试数据人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.9, source_group="SG-PS50-R1", origin_evidence="OR-PS50-R1"),
            )),
        ),
        required_claims=(
            {"actor": "测试账号A", "predicate": "threatening_message", "target_person": target, "status": "supported"},
            {"actor": actor, "predicate": "sender_attribution", "status": "opposing_dominant"},
        ),
        expected_abstention=True,
        required_legal_articles=("第五十条",),
        required_issue_types=("actor_attribution_gap",),
    )


def _ps83() -> CaseSpec:
    case_id = "PS-83"
    event = "EVT-PS-83-01"
    actor = "测试种植者甲"
    return CaseSpec(
        case_id=case_id,
        short_name="主动清除例外",
        law_key="public_security_law",
        law_title="中华人民共和国治安管理处罚法",
        article="第八十三条",
        complexity_type="statutory_exception",
        case_type_hint="禁止种植物核查",
        summary="种植事实和主动清除事实均被承认并有记录支持，法律例外与处罚结论仍留给人工审查。",
        materials=(
            _statement(case_id, "S1", "发现人员笔录.docx", "发现人员询问笔录", "reporting_party", (("你最初发现了什么？", "我看到测试区域内有若干待鉴别植物，之后通知测试种植者甲核对。"), ("后来如何处理？", "其在检查人员到场前主动拔除并封存。")), (
                _fact(actor=actor, object_entity="待鉴别植物A", predicate="cultivation_conduct", behavior="发现人员称测试种植者甲管理的区域存在待鉴别植物A", event_id=event, declarant="测试发现人员", declarant_role="witness", source_group="SG-PS83-S1", origin_evidence="OR-PS83-S1"),
                _fact(actor=actor, object_entity="待鉴别植物A", predicate="voluntary_removal", behavior="发现人员称测试种植者甲在检查前主动拔除并封存", event_id=event, declarant="测试发现人员", declarant_role="witness", source_group="SG-PS83-S1", origin_evidence="OR-PS83-S1"),
            )),
            _statement(case_id, "S2", "测试种植者甲笔录.docx", "相关人员询问笔录", "alleged_actor", (("植物是否由你种植管理？", "是，我承认由我种植管理，当时不清楚具体类别。"), ("何时清除？", "收到鉴别提醒后，我在检查人员到场前主动全部拔除并封存。")), (
                _fact(actor=actor, object_entity="待鉴别植物A", predicate="cultivation_conduct", behavior="测试种植者甲承认种植管理待鉴别植物A", event_id=event, declarant=actor, declarant_role="alleged_actor", source_group="SG-PS83-S2", origin_evidence="OR-PS83-S2"),
                _fact(actor=actor, object_entity="待鉴别植物A", predicate="voluntary_removal", behavior="测试种植者甲承认在检查前主动全部拔除并封存", event_id=event, declarant=actor, declarant_role="alleged_actor", source_group="SG-PS83-S2", origin_evidence="OR-PS83-S2"),
            )),
            _report(case_id, "R1", "现场检查与植物检验报告.docx", "现场检查与植物检验报告", ("检查人员到场时，现场种植位置已清空，封存袋中有待鉴别植物样本。", "时间记录显示主动拔除和封存发生在现场检查开始前。", "检验仅确认样本类别和数量范围，不对是否适用法律例外或处罚作出结论。"), (
                _fact(actor=actor, object_entity="待鉴别植物A", predicate="cultivation_conduct", behavior="现场位置和封存样本记录支持此前存在种植管理行为", event_id=event, declarant="测试检验人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.92, source_group="SG-PS83-R1", origin_evidence="OR-PS83-R1"),
                _fact(actor=actor, object_entity="待鉴别植物A", predicate="voluntary_removal", behavior="时间记录支持主动清除发生在检查开始前", event_id=event, declarant="测试检验人员", declarant_role="report_author", assertion_role="objective_report", evidence_category="report_image", confidence=0.94, source_group="SG-PS83-R1", origin_evidence="OR-PS83-R1"),
            )),
        ),
        required_claims=(
            {"actor": actor, "predicate": "cultivation_conduct", "object": "待鉴别植物A", "status": "supported"},
            {"actor": actor, "predicate": "voluntary_removal", "object": "待鉴别植物A", "status": "supported"},
        ),
        expected_abstention=True,
        required_legal_articles=("第八十三条",),
    )
