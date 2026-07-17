import unittest

from case_agent_demo.domain_affinity import CaseDomainRouter, DomainAffinityIndexer
from case_agent_demo.models import CaseGraph, EvidenceClaim, EvidenceNode, LegalChunk


class DomainAffinityTests(unittest.TestCase):
    def test_scores_text_and_case_domains(self):
        affinities = DomainAffinityIndexer().score_text("故意伤害 轻伤二级 鉴定意见")
        graph_domains = CaseDomainRouter().infer_domains(
            "故意伤害类案件",
            CaseGraph(claims=[EvidenceClaim("C1", "李四", "injury_grade")]),
        )

        self.assertTrue(any(item.domain_id == "criminal_injury" for item in affinities))
        self.assertTrue(any(item.domain_id == "personal_rights" for item in graph_domains))

    def test_chunk_gets_domain_affinity(self):
        chunk = LegalChunk("C1", "D1", "询问笔录真实性合法性审查，辨认程序应当规范。", title="证据规则")

        affinities = DomainAffinityIndexer().score_chunk(chunk)

        self.assertTrue(any(item.domain_id in {"procedure_compliance", "evidence_review", "identification"} for item in affinities))

    def test_routes_identification_from_structured_material_metadata(self):
        graph = CaseGraph(
            nodes=[
                EvidenceNode(
                    "F1",
                    "fact",
                    "P1",
                    "evidence_image",
                    "结构化观察",
                    metadata={"evidence_category": "identification"},
                )
            ]
        )

        domains = CaseDomainRouter().infer_domains("", graph)

        self.assertTrue(any(item.domain_id == "identification" for item in domains))


if __name__ == "__main__":
    unittest.main()
