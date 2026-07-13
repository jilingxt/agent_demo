from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableLambda

from case_agent_demo.graph_store import GraphStoreTool
from case_agent_demo.models import (
    CaseGraph,
    CaseTypeSuggestion,
    Challenge,
    Conflict,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    Fact,
    LegalMatch,
    Material,
    MaterialType,
    ReviewResult,
    fact_to_node,
    infer_claim_types,
    infer_predicate_stance,
)
from case_agent_demo.config import ModelProfile, ModelProfiles
from case_agent_demo.material_plan import MaterialPlan
from case_agent_demo.relation_tools import RelationRuleTool
from case_agent_demo.tools import LegalRetrievalTool, RagLegalAgent
from case_agent_demo.vision_tools import ImageEvidenceDescription


def _find_person(text: str) -> str:
    normalized = re.sub(r"\s+", "", text)
    label_patterns = [
        r"报警人([\u4e00-\u9fa5]{2,4}?)(?=称|报称|反映|，|,|。|$)",
        r"嫌疑人([\u4e00-\u9fa5]{2,4}?)(?=首先|先|将|把|与|和|，|,|。|$)",
        r"被询问人([\u4e00-\u9fa5]{2,4}?)(?=问[:：]|男|女|，|,|。|$)",
        r"被鉴定人[:：]?([\u4e00-\u9fa5]{2,4}?)(?=，|,|。|男|女|所受|$)",
        r"受害人([\u4e00-\u9fa5]{2,4}?)(?=被|被鉴定|，|,|。|$)",
        r"答[:：]?我叫([\u4e00-\u9fa5]{2,4}?)(?=，|,|。|男|女|$)",
    ]
    for pattern in label_patterns:
        match = re.search(pattern, normalized)
        if match:
            person = _clean_person_candidate(match.group(1))
            if person:
                return person

    match = re.search(r"([\u4e00-\u9fa5]{2,3})(?:(?<!所)称|出现在|没有|参与)", normalized)
    if not match:
        return "未识别人员"
    person = _clean_person_candidate(match.group(1))
    if not person:
        return "未识别人员"
    if len(person) == 3 and person[0] in "年月日时分秒点第":
        return person[1:]
    return person


def _clean_person_candidate(candidate: str) -> str:
    person = candidate.strip("：:，,。；;、 ")
    if len(person) == 3 and person[-1] in "趁从使等在存连又砸投拿":
        person = person[:-1]
    bad_fragments = (
        "我", "你", "他", "她", "其", "本所", "我所", "首先", "之后", "工作", "司法", "鉴定",
        "车辆", "金属", "危险", "报告", "现场", "明确", "功能", "结果", "人员", "衣领", "就用",
        "石岩", "又把", "关系",
    )
    if any(fragment in person for fragment in bad_fragments):
        return ""
    return person


_COMMON_SURNAME = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程邢裴陆荣翁荀羊惠甄曲封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲台从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
_PERSON_NAME_RE = re.compile(rf"[{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}}")


def _named_people(text: str) -> list[str]:
    normalized = _compact_text(text)
    name = rf"([{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}})"
    patterns = (
        rf"(?:被询问人|嫌疑人|行为人|违法行为人|被告人|受害人|被害人|被侵害人|被鉴定人)[:：]?\s*{name}",
        rf"(?:我叫|同事|朋友|证人)\s*{name}",
        rf"(?:显示|表明|记录|可见)\s*{name}",
        rf"(?:与|和|把|将|对|向)\s*{name}(?=的|发生|拉|拽|抱|殴打|击打|推|掐|拿|偷|摔|砸|损坏|转账|汇款|付款|支付|声称|[，。；;\s])",
        rf"(?:^|[，。；;\s]){name}(?=[^，。；;]{{0,20}}(?:拉|拽|抱摔|殴打|击打|推搡|掐|拿走|窃取|偷走|摔坏|砸坏|损坏|投放|放火|引爆|起哄|冲闯|扰乱|虚构|隐瞒|谎称|声称|欺骗|骗取|转账|汇款|付款|支付|被))",
        rf"{name}(?=[^，。；;]{{0,4}}(?:拉|拽|抱摔|殴打|击打|推搡|掐|拿走|窃取|偷走|摔坏|砸坏|损坏|投放|放火|引爆|起哄|冲闯|扰乱|虚构|隐瞒|谎称|声称|欺骗|骗取|转账|汇款|付款|支付))",
    )
    names: list[str] = []
    for pattern in patterns:
        for value in re.findall(pattern, normalized):
            candidate = _clean_person_candidate(value)
            if candidate and candidate not in names:
                names.append(candidate)
    return sorted(names, key=normalized.find)

def _find_time(text: str) -> str:
    match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日(?:\d{1,2}时(?:\d{1,2}分)?许?)?)", text)
    if match:
        return match.group(1)
    match = re.search(r"(\d{1,2}时(?:\d{1,2}分)?许?)", text)
    return match.group(1) if match else ""


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _shorten(text: str, limit: int = 110) -> str:
    text = _compact_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，,；;、 ") + "…"


def _extract_answer(text: str, question_keyword: str) -> str:
    pattern = rf"问[:：][^问答]{{0,80}}{re.escape(question_keyword)}[^答]{{0,80}}答[:：](.*?)(?=问[:：]|$)"
    match = re.search(pattern, text, flags=re.S)
    return match.group(1).strip() if match else ""


def _find_location(text: str) -> str:
    normalized = _compact_text(text)
    known_locations = ("深圳市宝安区新凯飞汽配", "新凯飞汽配", "石岩派出所")
    for location in known_locations:
        if location in normalized:
            return location
    patterns = [
        r"在([^，。；;]{2,40}?)(?:发生|，|,)",
        r"地点[:：]?([^，。；;]{2,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            location = match.group(1).strip()
            if location.startswith("在"):
                location = location[1:]
            return location
    return "现场" if "现场" in normalized else ""


def _find_named_actor(text: str, fallback: str) -> str:
    normalized = _compact_text(text)
    role_match = re.search(
        r"(?:嫌疑人|行为人|违法行为人|被告人)[:：]?\s*([\u4e00-\u9fa5]{2,4}?)(?=首先|先|实施|将|把|拉|拽|抱摔|殴打|击打|推|掐|拿|偷|摔|砸|损坏|投放|放火|引爆|起哄|冲闯|扰乱|，|。|\s|$)",
        normalized,
    )
    if role_match:
        return _clean_person_candidate(role_match.group(1)) or fallback
    action = r"(?:拉住|拉拽|拉|拽住|拽倒|拽|抱摔|殴打|击打|推搡|推|掐住|掐脖子|掐|拿走|窃取|偷走|摔坏|摔|砸坏|砸|损坏|投放|放火|引爆|起哄|冲闯|扰乱|虚构|隐瞒|谎称|声称|欺骗|骗取|转账|汇款|付款|支付|交付)"
    collective_actor = re.search(
        rf"(?:^|[，。；;\s])([{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}})等(?:人|多人)?[^，。；;]{{0,24}}{action}",
        normalized,
    )
    if collective_actor:
        return _clean_person_candidate(collective_actor.group(1)) or fallback
    names = _named_people(normalized)
    observed = re.search(
        rf"(?:我|本人)(?:在[^，。；;]{{0,12}})?(?:看到|看见|目睹)({rf'[{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}}'})[^，。；;]{{0,12}}{action}",
        normalized,
    )
    if observed:
        return _clean_person_candidate(observed.group(1)) or fallback
    if re.search(
        rf"(?:^|[，。；;\s])(?:我|本人)(?:先|又|随后|就)?[^，。；;]{{0,10}}{action}",
        normalized,
    ):
        return fallback
    direct_actors = []
    for name in names:
        match = re.search(
            rf"{re.escape(name)}([^，。；;]{{0,6}}?){action}",
            normalized,
        )
        if match:
            direct_actors.append((len(match.group(1)), normalized.find(name), name))
    if direct_actors:
        return min(direct_actors)[2]
    for possible_actor in names:
        for possible_target in names:
            if possible_actor == possible_target:
                continue
            if re.search(
                rf"{re.escape(possible_actor)}[^，。；;]{{0,16}}(?:把|将){re.escape(possible_target)}[^，。；;]{{0,6}}{action}",
                normalized,
            ):
                return possible_actor
    for name in names:
        if re.search(rf"{re.escape(name)}[^，。；;]{{0,24}}{action}", normalized) and not re.search(
            rf"{re.escape(name)}被[^，。；;]{{0,12}}{action}", normalized
        ):
            return name
    return fallback or _find_person(text)


def _find_injury(text: str) -> str:
    injuries = []
    for keyword in ("轻伤二级", "双侧鼻骨", "鼻骨骨折", "鼻中隔骨折", "眼角肿包流血", "肿包流血", "皮下瘀血", "软组织挫伤"):
        if keyword in text and keyword not in injuries:
            injuries.append(keyword)
    return "、".join(injuries)


def _find_victim(text: str, actor: str = "") -> str:
    normalized = _normalize_text(text)
    for label in ("受害人", "被害人", "被侵害人", "被鉴定人"):
        match = re.search(
            rf"{label}[:：]?([\u4e00-\u9fa5]{{2,4}}?)(?=首先|先|将|把|拉|拽|抱摔|殴打|击打|推|掐|拿|偷|摔|砸|损坏|问[:：]|男|女|，|。|\s|$)",
            normalized,
        )
        if match:
            candidate = _clean_person_candidate(match.group(1))
            if candidate and candidate != actor:
                return candidate
    for name in _named_people(normalized):
        if name != actor:
            return name
    return ""


def _find_action_target(text: str, actor: str, declarant: str = "") -> str:
    normalized = _compact_text(text)
    explicit_role = re.search(
        r"(?:受害人|被害人|被侵害人|被鉴定人)[:：]?\s*([\u4e00-\u9fa5]{2,4}?)(?=首先|先|将|把|拉|拽|抱摔|殴打|击打|推|掐|拿|偷|摔|砸|损坏|，|。|\s|$)",
        normalized,
    )
    if explicit_role and explicit_role.group(1) != actor:
        return explicit_role.group(1)
    role_target = _find_victim(normalized, actor)
    name_pattern = rf"[{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}}"
    actions = r"(?:拉住|拉拽|拽住|拽倒|抱摔|殴打|击打|推搡|掐住|掐脖子)"
    patterns = []
    if actor:
        patterns.append(
            rf"{re.escape(actor)}[^，。；;]{{0,16}}(?:把|将)({name_pattern})[^，。；;]{{0,6}}{actions}"
        )
        patterns.append(
            rf"{re.escape(actor)}[^，。；;]{{0,12}}{actions}[^，。；;]{{0,6}}({name_pattern})"
        )
    patterns.append(rf"{actions}(?:了)?({name_pattern})")
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match and match.group(1) != actor:
            return match.group(1)
    if declarant and declarant != actor and re.search(r"(?:我的|将我|把我|对我)", normalized):
        return declarant
    return role_target


def _find_relation_target(text: str, actor: str, verbs: tuple[str, ...]) -> str:
    normalized = _compact_text(text)
    name = rf"[{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}}"
    verb = "(?:" + "|".join(re.escape(item) for item in verbs) + ")"
    patterns = []
    if actor:
        patterns.append(
            rf"{re.escape(actor)}[^，。；;]{{0,12}}(?:向|对)({name})[^，。；;]{{0,12}}{verb}"
        )
    patterns.extend(
        (
            rf"(?:向|对)({name})[^，。；;]{{0,10}}{verb}",
            rf"{verb}(?:了)?({name})",
        )
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match and match.group(1) != actor:
            return match.group(1)
    return ""


def _find_directional_parties(
    text: str,
    verbs: tuple[str, ...],
    *,
    max_gap: int = 8,
) -> tuple[str, str] | None:
    normalized = _compact_text(text)
    name = rf"([{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}})"
    verb = "(?:" + "|".join(re.escape(item) for item in verbs) + ")"
    match = re.search(
        rf"{name}(?:向|对){name}(?:账户)?[^，。；;]{{0,{max_gap}}}{verb}",
        normalized,
    )
    if not match:
        return None
    return match.group(1), match.group(2)


def _find_event_id(text: str) -> str:
    explicit = re.search(r"(?:事件编号|案件编号|警情编号)[:：]?\s*([A-Za-z0-9_-]{4,64})", text)
    if explicit:
        return explicit.group(1)
    occurred = _find_time(text)
    date = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", occurred)
    if date:
        location = re.sub(r"\W+", "", _find_location(text))[:30]
        if location:
            return (
                f"DATE-{int(date.group(1)):04d}{int(date.group(2)):02d}{int(date.group(3)):02d}"
                f"-{location}"
            )
    return ""


def _find_explicit_event_id(text: str) -> str:
    explicit = re.search(r"(?:事件编号|案件编号|警情编号)[:：]?\s*([A-Za-z0-9_-]{4,64})", text)
    return explicit.group(1) if explicit else ""


def _semantic_assertions(
    *,
    material: Material,
    declarant: str,
    actor: str,
    target_person: str,
    predicate: str,
    obj: str,
    text: str,
) -> list[dict[str, Any]]:
    event_id = (
        _find_explicit_event_id(material.content)
        or _find_event_id(text)
        or f"MATERIAL-{material.material_id}"
    )
    declarant_role = str(
        material.metadata.get("declarant_role") or _infer_declarant_role(material.content)
    )
    base_stance = infer_predicate_stance(text, predicate)
    assertion_role = _material_assertion_role(material, declarant_role, base_stance)
    base = {
        "actor": actor,
        "target_person": target_person,
        "object": obj,
        "event_id": event_id,
        "stance": base_stance,
        "source_group": material.material_id,
        "origin_evidence": material.material_id,
        "declarant": declarant,
        "declarant_role": declarant_role,
        "assertion_role": assertion_role,
        "evidence_category": material.metadata.get(
            "evidence_category", material.material_type.value
        ),
    }
    assertions = [{**base, "predicate": predicate}]
    contextual_predicates = {
        "deceptive_representation",
        "mistaken_belief",
        "property_disposition",
        "property_loss",
        "prior_possession",
        "possession_transfer",
        "property_trace",
        "alternative_explanation",
        "damage_exists",
        "public_order_conduct",
        "public_context",
        "operational_impact",
        "persistence_or_group",
        "hazardous_conduct",
        "dangerous_object_or_condition",
        "exposure",
        "control_failure",
        "duty_record_present",
        "qualification_record_present",
        "authorization_record_absent",
        "conduct_recorded",
    }
    for inferred in infer_claim_types(text, obj):
        if inferred in contextual_predicates and inferred != predicate:
            if (
                inferred == "property_disposition"
                and material.material_type != MaterialType.STATEMENT
                and _find_directional_parties(
                    text,
                    ("转账", "汇款", "付款", "支付", "交付"),
                    max_gap=2,
                )
                is None
            ):
                continue
            inferred_stance = infer_predicate_stance(text, inferred)
            assertion = {
                **base,
                "predicate": inferred,
                "stance": inferred_stance,
                "assertion_role": _material_assertion_role(
                    material, declarant_role, inferred_stance
                ),
            }
            if inferred in {"mistaken_belief", "property_disposition", "property_loss"}:
                assertion.update(
                    actor=declarant,
                    target_person=actor if actor != declarant else target_person,
                )
            assertions.append(assertion)
    result_terms = ("受伤", "流血", "骨折", "轻伤", "重伤", "损伤", "肿包")
    if target_person and any(term in text for term in result_terms) and predicate == "violence":
        assertions.append(
            {
                **base,
                "actor": target_person,
                "target_person": target_person,
                "object": _find_injury(text),
                "predicate": "injury_consequence",
            }
        )
    relation_target = target_person or obj
    if relation_target and any(
        term in text
        for term in ("形成机制与", "作用机制与", "机制吻合", "机制一致", "相吻合", "受击位置一致")
    ):
        assertions.append({**base, "predicate": "mechanism_compatible"})
    if relation_target and any(term in text for term in ("随即", "立即", "当场", "紧接着", "五秒后", "5秒后")):
        assertions.append({**base, "predicate": "temporal_proximity"})
    return list({
        (item["actor"], item["predicate"], item["target_person"], item["event_id"]): item
        for item in assertions
    }.values())


def _find_object(text: str, candidates: tuple[str, ...]) -> str:
    for item in candidates:
        if item in text:
            return item
    return ""


def _find_money_amount(text: str) -> str:
    match = re.search(r"([零一二三四五六七八九十百千万亿两\d,.]+(?:万|亿)?元)", text)
    return match.group(1) if match else ""


def _infer_declarant_role(text: str) -> str:
    if any(label in text for label in ("报警人", "报案人", "被害人", "受害人", "被侵害人", "权利人", "占有人")):
        return "reporting_person"
    if any(label in text for label in ("嫌疑人", "行为人", "违法行为人", "被告人")):
        return "alleged_actor"
    if "证人" in text:
        return "witness"
    return ""


def _material_assertion_role(
    material: Material,
    declarant_role: str,
    stance: str,
) -> str:
    if material.material_type != MaterialType.STATEMENT:
        return "evidence_observation"
    if declarant_role == "reporting_person" and stance == "affirm":
        return "allegation"
    if declarant_role == "alleged_actor" and stance == "deny":
        return "defense_response"
    if declarant_role in {"alleged_actor", "witness"}:
        return "statement_evidence"
    return "allegation" if stance == "affirm" else "defense_response"


def _find_property_actor(text: str, fallback_person: str) -> str:
    normalized = _compact_text(text)
    for name in _named_people(normalized):
        if name in normalized and re.search(rf"{name}[^，。；;]{{0,12}}(?:把|将)", normalized):
            return name
        if re.search(rf"{name}[^，。；;]{{0,16}}(?:拿走|拿取|偷走|窃取|摔坏|砸坏|损坏)", normalized):
            return name
    if re.search(r"他(?:来|到|上前|走到)[^，。；;]{0,16}(?:把|将)", normalized):
        actor = _find_victim(normalized, fallback_person)
        if actor:
            return actor
    if re.search(r"(?:我|本人)[^，。；;]{0,8}(?:把|将)", normalized):
        return fallback_person
    return fallback_person or _find_person(normalized)


def _summarize_property_text(text: str, fallback_person: str) -> tuple[str, str] | None:
    normalized = _compact_text(text)
    obj = _find_object(normalized, ("手机", "门锁", "车辆", "电脑", "背包", "现金", "财物", "物品"))
    if not obj:
        return None

    actor = _find_property_actor(normalized, fallback_person)
    damage_terms = ("摔坏", "砸坏", "毁坏", "损坏", "屏幕损坏", "摔在地上")
    taking_terms = ("拿走", "拿取", "偷走", "窃取", "秘密窃取")
    if any(term in normalized for term in damage_terms):
        verb = "损坏"
        if "摔" in normalized:
            verb = "摔坏"
        elif "砸" in normalized:
            verb = "砸坏"
        behavior = f"{actor}{verb}{obj}"
        if "损坏" in normalized and "损坏" not in behavior:
            behavior += f"并造成{obj}损坏"
        return behavior, obj
    if any(term in normalized for term in taking_terms):
        return f"{actor}拿走{obj}", obj
    return None


def _statement_primary_actor(full_text: str, event_text: str, declarant: str) -> str:
    compact = _compact_text(full_text)
    if re.search(r"(?:有没有殴打|有无动手|有没有打架)[^答]{0,60}答[:：]?\s*(?:我有|有的|有)", compact):
        return declarant
    related = _counterparty_names(full_text, declarant)
    others = related or [name for name in _named_people(full_text) if name != declarant]
    if others and re.search(
        r"答[:：]?\s*我没有[^问]{0,30}(?:他|对方)[^问]{0,12}(?:打|殴打|动手)",
        compact,
    ):
        return others[0]
    if others and re.search(r"(?:之后|随后|然后)(?:他|对方)[^，。；;]{0,20}(?:拉|拽|抱摔|殴打|击打)", event_text):
        return others[0]
    return _find_named_actor(event_text, declarant)


def _counterparty_names(text: str, declarant: str) -> list[str]:
    normalized = _compact_text(text)
    name = rf"([{_COMMON_SURNAME}][\u4e00-\u9fa5]{{1,2}})"
    values = re.findall(
        rf"(?:同事|受害人|被害人|被侵害人|嫌疑人|行为人|被告人|被鉴定人)[:：]?\s*{name}",
        normalized,
    )
    return [
        candidate
        for value in values
        if (candidate := _clean_person_candidate(value)) and candidate != declarant
    ]


def _summarize_assault_text(
    text: str,
    fallback_person: str,
    actor_hint: str = "",
) -> tuple[str, str]:
    normalized = _compact_text(text)
    actor = actor_hint or _find_named_actor(normalized, fallback_person)
    victim = _find_action_target(normalized, actor, fallback_person)
    if not victim and fallback_person and fallback_person != actor:
        victim = fallback_person
    actions: list[str] = []
    if any(word in normalized for word in ("拉他的衣领", "拉后衣领", "拽住", "拽倒", "拉到在地", "拉倒在地")):
        actions.append("拉拽衣领并拽倒")
    if "推搡" in normalized:
        actions.append("互相推搡")
    if "抱摔" in normalized or ("抱着" in normalized and "摔" in normalized):
        actions.append("抱摔")
    if "掐" in normalized and "脖子" in normalized:
        actions.append("掐脖子")
    injury = _find_injury(normalized)
    if actions:
        target = victim or "对方"
        behavior = f"{actor}{'、'.join(actions)}{target}"
        if injury:
            behavior += f"，造成{injury}"
        elif any(word in normalized for word in ("受伤", "流血", "撞击地面")):
            behavior += "并致其受伤"
        return _shorten(behavior), f"{target} {injury}".strip()
    return _shorten(normalized), injury


def _summarize_statement_fact(material: Material) -> Fact:
    person = _find_person(material.content)
    event_text = (
        _extract_answer(material.content, "事情经过")
        or _extract_answer(material.content, "具体是怎么")
        or _extract_answer(material.content, "伤是如何造成")
        or material.content
    )
    property_summary = _summarize_property_text(event_text, person)
    assault_terms = ("拉", "拽", "抱摔", "殴打", "击打", "推搡", "掐", "打架", "动手")
    is_assault = any(term in event_text for term in assault_terms)
    if property_summary:
        behavior, obj = property_summary
    elif is_assault:
        assault_actor = _statement_primary_actor(material.content, event_text, person)
        behavior, obj = _summarize_assault_text(
            event_text,
            person,
            assault_actor,
        )
    else:
        behavior = _shorten(event_text)
        obj = _find_object(event_text, ("手机", "车辆", "现金", "财物", "危险物质", "爆炸物"))
        obj = obj or _find_money_amount(event_text)
    actor = assault_actor if is_assault and not property_summary else _find_named_actor(behavior, person)
    if property_summary or not is_assault:
        target = ""
    elif actor == person:
        counterparties = _counterparty_names(material.content, person)
        target = counterparties[0] if counterparties else _find_action_target(material.content, actor, person)
    elif any(term in material.content for term in ("证人证言", "我看到", "我看见", "我目睹")):
        target = _find_action_target(material.content, actor, person)
    else:
        target = person
    predicate = "property_damage" if property_summary and any(term in behavior for term in ("损坏", "摔坏", "砸坏")) else (
        "taking_property" if property_summary else (
            "violence" if is_assault else infer_claim_types(behavior, obj)[0]
        )
    )
    if predicate == "deceptive_representation" and actor != person:
        target = person
    if predicate == "deceptive_representation":
        directional = _find_directional_parties(
            event_text,
            ("谎称", "声称", "欺骗", "骗取"),
        )
        if directional:
            actor, target = directional
        target = _find_relation_target(
            event_text,
            actor,
            ("谎称", "声称", "欺骗", "骗取"),
        ) or target
    elif predicate == "property_disposition":
        directional = _find_directional_parties(
            event_text,
            ("转账", "汇款", "付款", "支付", "交付"),
            max_gap=2,
        )
        if directional:
            actor, target = directional
        target = _find_relation_target(
            event_text,
            actor,
            ("转账", "汇款", "付款", "支付", "交付"),
        ) or target
    assertions = _semantic_assertions(
        material=material,
        declarant=person,
        actor=actor,
        target_person=target,
        predicate=predicate,
        obj=obj,
        text=event_text,
    )
    return Fact(
        fact_id=f"F-{material.material_id}-TEXT",
        source_material_id=material.material_id,
        source_type=material.material_type.value,
        person=person,
        behavior=behavior,
        time=_find_time(event_text or material.content),
        location=_find_location(event_text or material.content),
        object=obj,
        confidence=0.86,
        metadata={**assertions[0], "assertions": assertions},
    )


def _extract_denial_facts(material: Material) -> list[Fact]:
    text = _compact_text(material.content)
    person = _find_person(material.content)
    victim = _find_victim(text, person)
    event_text = _extract_answer(material.content, "事情经过") or text
    patterns = [
        (r"有没有打架[^答]{0,40}答[:：]?\s*没有", "没有打架", "violence"),
        (r"有无动手[^答]{0,40}答[:：]?\s*没有", "没有动手", "violence"),
        (r"有没有殴打[^答]{0,40}答[:：]?\s*没有", "没有殴打", "violence"),
        (r"有没有拿[^答]{0,40}答[:：]?\s*没有", "没有拿取", "taking_property"),
        (r"有没有财物受损[^答]{0,40}答[:：]?\s*没有", "没有财物受损", "property_damage"),
        (r"有没有财务损坏[^答]{0,40}答[:：]?\s*没有", "没有财物损坏", "property_damage"),
        (r"有没有损坏[^答]{0,40}答[:：]?\s*没有", "没有损坏", "property_damage"),
        (r"现场有没有人受伤[^答]{0,40}答[:：]?\s*(?:没有|我没有[^，。；;]*，?[^。；;]*没有受伤)", "没有人受伤", "injury_consequence"),
    ]
    facts: list[Fact] = []
    declarant_role = str(
        material.metadata.get("declarant_role") or _infer_declarant_role(material.content)
    )
    for index, (pattern, behavior, _claim_type) in enumerate(patterns, start=1):
        if not re.search(pattern, text):
            continue
        facts.append(
            Fact(
                fact_id=f"F-{material.material_id}-DENIAL-{index}",
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=person,
                behavior=f"{person}称{behavior}",
                time=_find_time(event_text),
                location=_find_location(event_text),
                object=victim,
                confidence=0.84,
                metadata={
                    "actor": person,
                    "target_person": victim,
                    "predicate": _claim_type,
                    "event_id": _find_explicit_event_id(material.content) or _find_event_id(event_text),
                    "stance": "deny",
                    "source_group": material.material_id,
                    "origin_evidence": material.material_id,
                    "declarant": person,
                    "declarant_role": declarant_role,
                    "assertion_role": _material_assertion_role(
                        material, declarant_role, "deny"
                    ),
                    "evidence_category": material.metadata.get(
                        "evidence_category", material.material_type.value
                    ),
                },
            )
        )
    return facts


def _summarize_image_fact(material: Material, content: str, confidence: float) -> Fact:
    behavior, obj = _summarize_assault_text(content, _find_person(content))
    if not behavior or behavior == "未识别人员":
        behavior = _shorten(content.replace("图片内容：", "").replace("文字识别：", " "))
    return Fact(
        fact_id=f"F-{material.material_id}-PIC",
        source_material_id=material.material_id,
        source_type=material.material_type.value,
        person=_find_person(content),
        behavior=behavior,
        time=_find_time(content),
        location=_find_location(content),
        object=obj,
        confidence=confidence,
        metadata={
            **material.metadata,
            "assertion_role": "evidence_observation",
            "evidence_category": material.metadata.get(
                "evidence_category", material.material_type.value
            ),
        },
    )


def _summarize_report_fact(material: Material, content: str, confidence: float) -> Fact:
    if any(word in content for word in ("监控", "研判")):
        report_type = "监控研判报告"
    elif any(word in content for word in ("鉴定意见", "法医", "轻伤", "重伤")):
        report_type = "法医鉴定报告"
    else:
        report_type = "报告材料"
    person = _find_person(content)
    injury = _find_injury(content)
    if "鉴定意见" in content or "轻伤" in content:
        victim = _find_victim(content) or person
        behavior = f"{report_type}认定{victim}所受损伤为{injury or '需结合报告原文核对'}"
        obj = f"{victim} {injury}".strip()
        assertions = _semantic_assertions(
            material=material,
            declarant=person,
            actor=victim,
            target_person=victim,
            predicate="injury_grade",
            obj=injury,
            text=content,
        )
        for item in assertions:
            if item["predicate"] == "injury_grade":
                item["authority_candidate"] = True
    else:
        property_summary = _summarize_property_text(content, person)
        assault_terms = ("拉", "拽", "抱摔", "殴打", "击打", "推搡", "掐", "打架", "动手")
        is_assault = any(term in content for term in assault_terms)
        if property_summary:
            behavior, obj = property_summary
        elif is_assault:
            behavior, obj = _summarize_assault_text(content, person)
        else:
            behavior = _shorten(content)
            obj = _find_object(content, ("手机", "车辆", "现金", "财物", "危险物质", "爆炸物"))
            obj = obj or _find_money_amount(content)
        behavior = f"{report_type}显示{behavior}"
        actor = _find_named_actor(behavior, person)
        target = "" if property_summary or not is_assault else _find_action_target(content, actor, person)
        predicate = "property_damage" if property_summary and any(term in behavior for term in ("损坏", "摔坏", "砸坏")) else (
            "taking_property" if property_summary else (
                "violence" if is_assault else infer_claim_types(behavior, obj)[0]
            )
        )
        if property_summary and actor == "未识别人员" and any(
            term in content for term in ("损坏结果", "功能丧失", "维修损失")
        ):
            predicate = "damage_exists"
        if predicate == "deceptive_representation":
            directional = _find_directional_parties(
                content,
                ("谎称", "声称", "欺骗", "骗取"),
            )
            if directional:
                actor, target = directional
            target = _find_relation_target(
                content,
                actor,
                ("谎称", "声称", "欺骗", "骗取"),
            ) or target
        elif predicate == "property_disposition":
            directional = _find_directional_parties(
                content,
                ("转账", "汇款", "付款", "支付", "交付"),
                max_gap=2,
            )
            if directional:
                actor, target = directional
            target = _find_relation_target(
                content,
                actor,
                ("转账", "汇款", "付款", "支付", "交付"),
            ) or target
        assertions = _semantic_assertions(
            material=material,
            declarant=person,
            actor=actor,
            target_person=target,
            predicate=predicate,
            obj=obj,
            text=content,
        )
    return Fact(
        fact_id=f"F-{material.material_id}-REPORT",
        source_material_id=material.material_id,
        source_type=material.material_type.value,
        person=person,
        behavior=_shorten(behavior, 100),
        time=_find_time(content),
        location=_find_location(content),
        object=obj,
        confidence=confidence,
        metadata={**assertions[0], "assertions": assertions},
    )


def _should_use_vision_tool(material: Material) -> bool:
    content = material.content.strip()
    return bool(material.source_path and (not content or "Qwen" in content))


def _image_description_content(description: ImageEvidenceDescription) -> str:
    return description.to_material_content()


def _statement_user_input(material: Material) -> str:
    return (
        f"material_id: {material.material_id}\n"
        f"material_type: {material.material_type.value}\n"
        f"source_path: {material.source_path}\n\n"
        f"{material.content}"
    )


def _materials_user_input(materials: list[Material]) -> str:
    return "\n\n--- material ---\n\n".join(
        (
            f"material_id: {material.material_id}\n"
            f"material_type: {material.material_type.value}\n"
            f"source_path: {material.source_path}\n\n"
            f"{material.content}"
        )
        for material in materials
    )


def _case_type_suggestion_from_json(data: dict[str, Any]) -> CaseTypeSuggestion:
    suggestions = data.get("suggested_case_types", [])
    if not isinstance(suggestions, list):
        suggestions = []
    return CaseTypeSuggestion(
        suggested_case_types=[item for item in suggestions if isinstance(item, dict)],
        requires_human_confirmation=bool(data.get("requires_human_confirmation", True)),
    )


def _planning_fallback(materials: list[Material]) -> CaseTypeSuggestion:
    return PlanningAgent()._suggest(materials)


def _reasoning_user_input(payload: dict[str, Any]) -> str:
    graph: EvidenceGraph = payload["evidence_graph"]
    laws: list[LegalMatch] = payload["legal_matches"]
    conflicts: list[Conflict] = payload["conflicts"]
    fact_lines = "\n".join(
        (
            f"{fact.fact_id}|source={fact.source_material_id}|person={fact.person}|"
            f"behavior={fact.behavior}|time={fact.time}|location={fact.location}|object={fact.object}"
        )
        for fact in graph.facts
    )
    law_lines = "\n".join(f"{law.law_id}|{law.law_name}|{law.article}|{law.legal_element}" for law in laws)
    conflict_lines = "\n".join(f"{item.conflict_id}|{item.conflict_type}|{item.source_a}|{item.source_b}|{item.severity}" for item in conflicts)
    assessment_lines = _claim_assessment_text(payload)
    return (
        f"confirmed_case_type: {payload['confirmed_case_type']}\n\n"
        f"case_graph_facts:\n{fact_lines}\n\n"
        f"claim_assessments:\n{assessment_lines}\n\n"
        f"legal_matches:\n{law_lines}\n\n"
        f"conflicts:\n{conflict_lines}"
    )


def _reasoning_fallback(payload: dict[str, Any]) -> str:
    return ReasoningAgent().reason(payload)


def _claim_assessment_text(payload: dict[str, Any]) -> str:
    assessments = payload.get("claim_assessments") or []
    if not assessments:
        return "未提供 Claim 级评估。"
    return "\n".join(
        f"{item.claim_id}|status={item.status}|support_index={item.support_index}|"
        f"reasons={'；'.join(item.reasons)}"
        for item in assessments
    )


def _node_assessment_status(payload: dict[str, Any]) -> dict[str, str]:
    graph: EvidenceGraph = payload["evidence_graph"]
    status_by_claim = {
        item.claim_id: item.status
        for item in payload.get("claim_assessments") or []
    }
    result: dict[str, str] = {}
    for claim in graph.claims:
        status = status_by_claim.get(claim.claim_id, "")
        for node_id in (
            claim.supporting_node_ids
            + claim.opposing_node_ids
            + claim.ambiguous_node_ids
        ):
            result[node_id] = status
    return result


def _fact_assessment_prefix(status: str) -> str:
    return {
        "authority_anchored": "权威材料支持",
        "supported": "现有材料支持",
        "contested": "争议材料（尚不能作为确定事实）",
        "contested_but_not_refuted": "争议材料（尚不能作为确定事实）",
        "insufficient": "证据不足（待补强）",
        "opposing_dominant": "反向证据占优（不得作为确定事实）",
        "authority_contested": "权威意见存在争议",
    }.get(status, "待评估材料")


def _facts_from_json(data: dict[str, Any], material: Material) -> list[Fact]:
    raw_facts = data.get("facts", [])
    if not isinstance(raw_facts, list):
        return []
    facts: list[Fact] = []
    for index, item in enumerate(raw_facts, start=1):
        if not isinstance(item, dict):
            continue
        metadata = dict(item.get("metadata", {})) if isinstance(item.get("metadata"), dict) else {}
        for key in (
            "actor", "target_person", "predicate", "event_id", "stance", "source_group",
            "origin_evidence", "declarant", "assertions", "assertion_role",
            "declarant_role", "evidence_category", "modality",
        ):
            if key in item:
                metadata[key] = item[key]
        facts.append(
            Fact(
                fact_id=str(item.get("fact_id") or f"F-{material.material_id}-TEXT-{index}"),
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=str(item.get("person", "")),
                behavior=_shorten(str(item.get("behavior", "")), 120),
                time=str(item.get("time", "")),
                location=str(item.get("location", "")),
                object=str(item.get("object", "")),
                confidence=float(item.get("confidence", 0.8) or 0.8),
                metadata=metadata,
            )
        )
    return facts or TextAgent()._extract_fallback(material)

@dataclass
class PlanningAgent:
    name: str = "planning_agent"
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().planning

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self._suggest)

    def suggest(self, materials: list[Material]) -> CaseTypeSuggestion:
        return self.runnable.invoke(materials)

    def plan_materials(self, materials: list[Material]) -> MaterialPlan:
        return MaterialPlan.from_materials(materials)

    def _suggest(self, materials: list[Material]) -> CaseTypeSuggestion:
        if self.runtime is not None:
            return self.runtime.run_json(
                "planning_agent",
                self.profile,
                _materials_user_input(materials),
                fallback=lambda: _planning_fallback(materials),
                parser=_case_type_suggestion_from_json,
            )
        joined = "\n".join(item.content for item in materials)
        if any(word in joined for word in ("故意伤害", "殴打", "轻伤", "骨折", "抱摔")):
            case_type = "故意伤害类案件"
        elif any(word in joined for word in ("门锁", "盗窃", "占有")):
            case_type = "盗窃类案件"
        else:
            case_type = "待人工判断案件"
        return CaseTypeSuggestion(
            suggested_case_types=[
                {
                    "case_type": case_type,
                    "confidence": 0.82 if case_type != "待人工判断案件" else 0.5,
                    "basis": ["demo 根据材料关键词生成建议，需人工确认"],
                    "requires_human_confirmation": True,
                }
            ]
        )


@dataclass
class TextAgent:
    name: str = "text_agent"
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().text

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        if self.runtime is not None:
            return self.runtime.run_json(
                "text_agent",
                self.profile,
                _statement_user_input(material),
                fallback=lambda: self._extract_fallback(material),
                parser=lambda data: _facts_from_json(data, material),
            )
        return self._extract_fallback(material)

    def _extract_fallback(self, material: Material) -> list[Fact]:
        return [_summarize_statement_fact(material), *_extract_denial_facts(material)]


@dataclass
class PicAgent:
    name: str = "pic_agent"
    vision_tool: Any | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        content = material.content
        confidence = 0.9
        if self.vision_tool is not None and _should_use_vision_tool(material):
            description = self.vision_tool.describe(material)
            content = _image_description_content(description)
            confidence = description.confidence
        return self._fact_from_content(material, content, confidence)

    def extract_group(self, group_id: str, image_paths: list[str]) -> list[Fact]:
        if self.vision_tool is None:
            content = f"Image group pending Qwen vision: {group_id}"
            confidence = 0.0
        else:
            description = self.vision_tool.describe_group(group_id, image_paths)
            content = _image_description_content(description)
            confidence = description.confidence
        material = Material(group_id, MaterialType.EVIDENCE_IMAGE, content, source_path=";".join(image_paths))
        return self._fact_from_content(material, content, confidence)

    def _fact_from_content(self, material: Material, content: str, confidence: float) -> list[Fact]:
        return [_summarize_image_fact(material, content, confidence)]

@dataclass
class ReportImageAgent:
    name: str = "report_image_agent"
    legal_tool: LegalRetrievalTool | None = None
    vision_tool: Any | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        content = material.content
        if self.vision_tool is not None and _should_use_vision_tool(material):
            description = self.vision_tool.describe(material)
            content = _image_description_content(description)
        report_type = "监控研判报告" if any(word in content for word in ("监控", "研判")) else "法医检测报告"
        confidence = 0.93 if any(word in content for word in ("签章清晰", "结论", "报告", "鉴定意见", "轻伤")) else 0.78
        return [_summarize_report_fact(material, content, confidence)]

    def extract_group(self, group_id: str, image_paths: list[str]) -> list[Fact]:
        if self.vision_tool is None:
            content = f"Report image group pending Qwen vision: {group_id}"
        else:
            description = self.vision_tool.describe_group(group_id, image_paths)
            content = _image_description_content(description)
        material = Material(group_id, MaterialType.REPORT_IMAGE, content, source_path=";".join(image_paths))
        report_type = "report_image"
        confidence = 0.93 if any(word in content for word in ("结论", "报告", "鉴定意见", "轻伤")) else 0.78
        return [_summarize_report_fact(material, content, confidence)]


@dataclass
class EvidenceGraphAgent:
    name: str = "case_graph_agent"
    legal_tool: LegalRetrievalTool | None = None
    relation_tool: RelationRuleTool = field(default_factory=RelationRuleTool)

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.build)

    def add_fact(self, store: GraphStoreTool, fact: Fact) -> EvidenceNode:
        material_node = _material_node_for_fact(fact)
        fact_node = fact_to_node(fact)
        existing_nodes = [node for node in store.list_nodes() if node.node_type == "fact"]

        store.add_node(material_node)
        store.add_node(fact_node)
        store.add_edge(
            EvidenceEdge(
                edge_id=f"E-{material_node.node_id}-{fact_node.node_id}-source_of",
                source_node_id=material_node.node_id,
                target_node_id=fact_node.node_id,
                edge_type="source_of",
                reason="材料生成事实节点。",
                confidence=fact.confidence,
                evidence_basis=[fact.source_material_id, fact.fact_id],
            )
        )
        for edge in self.relation_tool.infer_edges_for_new_node(fact_node, existing_nodes):
            store.add_edge(edge)
        return fact_node

    def build(self, facts: list[Fact]) -> CaseGraph:
        store = GraphStoreTool()
        for fact in facts:
            self.add_fact(store, fact)
        return store.to_graph()


CaseGraphAgent = EvidenceGraphAgent


def _material_node_for_fact(fact: Fact) -> EvidenceNode:
    return EvidenceNode(
        node_id=f"M-{fact.source_material_id}",
        node_type="material",
        source_material_id=fact.source_material_id,
        source_type=fact.source_type,
        summary=f"材料 {fact.source_material_id}",
        confidence=1.0,
    )


@dataclass(frozen=True)
class _ConflictClaim:
    fact: Fact
    polarity: str
    claim_types: tuple[str, ...]
    object_key: str


def _classify_conflict_claim(fact: Fact) -> _ConflictClaim:
    text = f"{fact.person} {fact.behavior} {fact.object}".lower()
    claim_text = f"{fact.behavior} {fact.object}".lower()
    polarity = "deny" if _has_any(claim_text, ("没有", "未", "否认", "不承认", "不在", "没", "在家")) else "affirm"
    claim_types: list[str] = []
    if _has_any(text, ("到过现场", "在现场", "出现在现场", "看见", "在家")):
        claim_types.append("presence")
    if _has_any(text, ("打架", "动手", "殴打", "伤害", "抱摔", "拽倒", "拉拽", "推搡", "掐脖子")):
        claim_types.append("violence")
    if _has_any(text, ("拿", "拿走", "取走", "盗窃", "窃取", "占有")):
        claim_types.append("taking_property")
    if _has_any(text, ("损坏", "毁坏", "砸坏", "破坏")):
        claim_types.append("property_damage")
    if _has_any(text, ("受伤", "伤情", "轻伤", "重伤", "骨折", "流血", "瘀血", "挫伤", "鉴定意见")):
        claim_types.append("injury_consequence")
    if not claim_types:
        claim_types.append("general")
    return _ConflictClaim(
        fact=fact,
        polarity=polarity,
        claim_types=tuple(dict.fromkeys(claim_types)),
        object_key=_claim_object_key(fact, text),
    )


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _claim_object_key(fact: Fact, text: str) -> str:
    candidates = []
    for value in (fact.object, fact.person):
        if value:
            candidates.append(value)
    for keyword in ("贺显作", "李文杰", "手机", "门锁", "财物", "车辆", "背包"):
        if keyword in text:
            candidates.append(keyword)
    for candidate in candidates:
        cleaned = re.sub(r"\s+", "", candidate)
        if cleaned:
            return cleaned
    return ""


def _objects_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return left in right or right in left


def _claim_conflict_type(left: _ConflictClaim, right: _ConflictClaim) -> str:
    if left.polarity == right.polarity:
        return ""
    if not _objects_overlap(left.object_key, right.object_key):
        return ""
    left_types = set(left.claim_types)
    right_types = set(right.claim_types)
    if left_types & right_types:
        return "presence_conflict" if "presence" in left_types | right_types else "direct_fact_contradiction"
    if (
        ("violence" in left_types and "injury_consequence" in right_types)
        or ("injury_consequence" in left_types and "violence" in right_types)
    ):
        return "denial_vs_consequence"
    return ""


@dataclass
class ConflictAgent:
    name: str = "conflict_agent"

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.detect)

    def detect(self, graph: EvidenceGraph) -> list[Conflict]:
        conflicts: list[Conflict] = []
        claims = [_classify_conflict_claim(fact) for fact in graph.facts]
        counter = 1
        seen: set[tuple[str, str, str]] = set()
        for left in claims:
            for right in claims:
                if left.fact.fact_id == right.fact.fact_id:
                    continue
                conflict_type = _claim_conflict_type(left, right)
                if not conflict_type:
                    continue
                key = tuple(sorted((left.fact.fact_id, right.fact.fact_id))) + (conflict_type,)
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(
                    Conflict(
                        conflict_id=f"C-{counter}",
                        conflict_type=conflict_type,
                        claim_a=left.fact.behavior,
                        claim_b=right.fact.behavior,
                        source_a=left.fact.source_material_id,
                        source_b=right.fact.source_material_id,
                        severity="high",
                    )
                )
                counter += 1
        return conflicts


@dataclass
class _LegacyRagLegalAgent:
    name: str = "rag_legal_agent"

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.retrieve)

    def retrieve(self, payload: dict[str, Any]) -> list[LegalMatch]:
        case_type = payload["confirmed_case_type"]
        graph: EvidenceGraph = payload["evidence_graph"]
        behavior = "；".join(fact.behavior for fact in graph.facts[:3])
        return [
            LegalMatch(
                law_id="L-DEMO-1",
                law_name="中华人民共和国刑法",
                article="第二百三十四条（demo 预置）",
                legal_element="故意伤害他人身体的，需结合伤情、行为、因果关系等证据审查。",
                matched_behavior=f"{case_type} / {behavior}",
                source="demo 预置法条片段，未实现 RAG 入库",
            )
        ]


@dataclass
class ReasoningAgent:
    name: str = "reasoning_agent"
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().reasoning
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.reason)

    def retrieve_legal_matches(self, payload: dict[str, Any]) -> list[LegalMatch]:
        if self.legal_tool is None:
            return list(payload.get("legal_matches", []))
        return self.legal_tool.retrieve({**payload, "purpose": "reasoning_legal_basis"})

    def reason(self, payload: dict[str, Any]) -> str:
        if self.runtime is not None:
            return self.runtime.run_json(
                "reasoning_agent",
                self.profile,
                _reasoning_user_input(payload),
                fallback=lambda: _reasoning_fallback(payload),
                parser=lambda data: str(data.get("report", "")) or _reasoning_fallback(payload),
            )
        graph: EvidenceGraph = payload["evidence_graph"]
        laws: list[LegalMatch] = payload["legal_matches"]
        conflicts: list[Conflict] = payload["conflicts"]
        case_type = payload["confirmed_case_type"]
        status_by_node = _node_assessment_status(payload)
        fact_lines = "\n".join(
            f"- {_fact_assessment_prefix(status_by_node.get(fact.fact_id, ''))}："
            f"{fact.person or '未识别人员'}：{fact.behavior}（来源 {fact.source_material_id}）"
            for fact in graph.facts
        )
        time_location_lines = "\n".join(
            f"- {fact.source_material_id}：{fact.time or '时间待核实'}；{fact.location or '地点待核实'}"
            for fact in graph.facts
        )
        object_lines = "\n".join(
            f"- {fact.source_material_id}：{fact.object}"
            for fact in graph.facts
            if fact.object
        )
        if not object_lines:
            object_lines = "- 暂未提取到明确对象或后果。"
        law_lines = "\n".join(f"- {law.law_name}{law.article}：{law.legal_element}" for law in laws)
        if not law_lines:
            law_lines = "- 暂未匹配到静态法律依据。"
        conflict_lines = "\n".join(f"- {item.conflict_type}：{item.source_a} 与 {item.source_b} 需人工核对" for item in conflicts)
        if not conflict_lines:
            conflict_lines = "- 暂未发现结构化规则可识别的冲突。"
        case_type_context = payload.get("case_type_context")
        if case_type and getattr(case_type_context, "status", "confirmed") == "confirmed":
            case_heading = f"人工确认案件类型：{case_type}"
        else:
            domains = "、".join(getattr(case_type_context, "domains", []) or [])
            case_heading = f"自动识别事实领域：{domains or '尚未形成稳定分类'}"
        return (
            f"{case_heading}\n\n"
            f"现有证据显示（行为事实）：\n{fact_lines}\n\n"
            f"时间地点：\n{time_location_lines}\n\n"
            f"对象与后果：\n{object_lines}\n\n"
            f"可能关联的法律依据：\n{law_lines}\n\n"
            f"冲突与纰漏提示：\n{conflict_lines}\n\n"
            "结论边界：以上内容仅为基于现有材料的辅助分析，仍需人工复核和补强。"
        )

    def revise(self, draft_report: str, challenges: list[Challenge]) -> str:
        if not challenges:
            return draft_report + "\n\n反方质询：未发现需要修订的关键挑战。"
        challenge_lines = "\n".join(
            f"- {item.challenge_type}：{item.reason}（对象：{item.target}，需人工确认）"
            for item in challenges
        )
        return (
            f"{draft_report}\n\n"
            f"反方质询与修订：\n{challenge_lines}\n\n"
            "修订说明：以上争议点不作确定性结论，标记为需人工确认或需补强证据。"
        )


@dataclass
class JudgeAgent:
    name: str = "judge_agent"
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.challenge)

    def challenge(self, payload: dict[str, Any]) -> list[Challenge]:
        draft_report: str = payload["draft_report"]
        conflicts: list[Conflict] = payload["conflicts"]
        legal_matches: list[LegalMatch] = payload.get("legal_matches", [])
        if not legal_matches and self.legal_tool is not None:
            legal_matches = self.legal_tool.retrieve({**payload, "purpose": "judge_legal_challenge"})
        challenges: list[Challenge] = []
        for idx, conflict in enumerate(conflicts, start=1):
            if conflict.severity == "high":
                challenges.append(
                    Challenge(
                        challenge_id=f"J-{idx}",
                        challenge_type="unresolved_conflict",
                        target=conflict.conflict_id,
                        reason=f"高严重度冲突 {conflict.source_a}/{conflict.source_b} 需要 Reasoning 明确收窄结论。",
                        severity="high",
                    )
                )
        if any(phrase in draft_report for phrase in ("已经构成犯罪", "应当处罚", "必然构成")):
            challenges.append(
                Challenge(
                    challenge_id=f"J-{len(challenges) + 1}",
                    challenge_type="overstated_legal_conclusion",
                    target="draft_report",
                    reason="Reasoning 初稿包含最终性法律判断，必须改为辅助分析表述。",
                    severity="high",
                )
            )
        if not legal_matches:
            challenges.append(
                Challenge(
                    challenge_id=f"J-{len(challenges) + 1}",
                    challenge_type="missing_legal_basis",
                    target="legal_matches",
                    reason="缺少可追溯法条来源，不能进行法律要件匹配。",
                    severity="high",
                )
            )
        return challenges


@dataclass
class ReviewAgent:
    name: str = "review_agent"
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(lambda payload: self.review(**payload))

    def review(
        self,
        report: str,
        supporting_fact_ids: list[str],
        supporting_law_ids: list[str],
        challenges: list[Challenge] | None = None,
    ) -> ReviewResult:
        issues: list[str] = []
        forbidden_phrases = ("已经构成犯罪", "应当处罚", "必然构成", "依法应当追究")
        if any(phrase in report for phrase in forbidden_phrases):
            issues.append("包含最终性法律判断，demo 只能输出辅助分析。")
        if not supporting_fact_ids:
            issues.append("缺少证据事实来源。")
        if not supporting_law_ids:
            issues.append("缺少 RAG 法条来源。")
        high_challenges = [item for item in challenges or [] if item.severity == "high"]
        if high_challenges and "反方质询" not in report:
            issues.append("未回应 Judge Agent 提出的高严重度挑战。")
        return ReviewResult(status="FAIL" if issues else "PASS", issues=issues)
