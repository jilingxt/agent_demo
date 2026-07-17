from __future__ import annotations

import re
from typing import Any


class SemanticFixtureRuntime:
    """Return explicit test assertions by material ID; never parses material prose."""

    def __init__(self, facts_by_material_id: dict[str, list[dict[str, Any]]]):
        self.facts_by_material_id = facts_by_material_id

    def run_json(self, prompt_name, profile, user_input, fallback, parser):
        del prompt_name, profile, fallback
        match = re.search(r"material_id:\s*([^\r\n]+)", user_input)
        material_id = match.group(1).strip() if match else ""
        return parser({"facts": self.facts_by_material_id.get(material_id, [])})


def semantic_fact(
    *,
    actor: str,
    predicate: str,
    behavior: str,
    stance: str = "affirm",
    target_person: str = "",
    object: str = "",
    declarant: str = "",
    declarant_role: str = "unknown",
    assertion_role: str = "statement_evidence",
    event_id: str = "",
    evidence_category: str = "statement",
    confidence: float = 0.86,
    **extra,
) -> dict[str, Any]:
    return {
        "person": declarant or actor,
        "declarant": declarant,
        "declarant_role": declarant_role,
        "actor": actor,
        "target_person": target_person,
        "predicate": predicate,
        "stance": stance,
        "assertion_role": assertion_role,
        "behavior": behavior,
        "object": object,
        "event_id": event_id,
        "source_group": extra.pop("source_group", ""),
        "origin_evidence": extra.pop("origin_evidence", ""),
        "evidence_category": evidence_category,
        "evidence_span": extra.pop("evidence_span", behavior),
        "confidence": confidence,
        **extra,
    }
