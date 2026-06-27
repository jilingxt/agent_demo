import unittest
from unittest.mock import patch

from argparse import Namespace

from case_agent_demo.cli import attach_qwen_vision_tool, should_enable_qwen_vision
from case_agent_demo.workflow import CaseWorkflow


class CliQwenVisionTests(unittest.TestCase):
    def test_attach_qwen_vision_tool_sets_pic_and_report_agents(self):
        workflow = CaseWorkflow.demo()
        fake_tool = object()

        with patch("case_agent_demo.cli.QwenImageEvidenceTool.from_config_file", return_value=fake_tool):
            attach_qwen_vision_tool(workflow)

        self.assertIs(workflow.pic_agent.vision_tool, fake_tool)
        self.assertIs(workflow.report_image_agent.vision_tool, fake_tool)

    def test_qwen_vision_is_enabled_by_default_for_evidence_dir(self):
        args = Namespace(evidence_dir="evidence_vault", disable_qwen_vision=False)

        self.assertTrue(should_enable_qwen_vision(args))

    def test_qwen_vision_is_not_enabled_for_sample_only(self):
        args = Namespace(evidence_dir=None, disable_qwen_vision=False)

        self.assertFalse(should_enable_qwen_vision(args))

    def test_qwen_vision_can_be_disabled_for_evidence_dir(self):
        args = Namespace(evidence_dir="evidence_vault", disable_qwen_vision=True)

        self.assertFalse(should_enable_qwen_vision(args))


if __name__ == "__main__":
    unittest.main()
