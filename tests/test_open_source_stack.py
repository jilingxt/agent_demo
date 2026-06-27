import unittest
from pathlib import Path

from case_agent_demo.open_source_stack import OpenSourceStack
from case_agent_demo.workflow import CaseWorkflow


class OpenSourceStackTests(unittest.TestCase):
    def test_selected_repositories_are_declared_with_roles(self):
        stack = OpenSourceStack.default()

        self.assertEqual(stack.component("langgraph").role, "workflow_orchestration")
        self.assertEqual(stack.component("llama_index").role, "rag_and_retrieval")
        self.assertEqual(stack.component("docling").role, "document_preprocessing_optional")
        self.assertEqual(stack.component("agent-wiz").role, "security_review")

    def test_components_are_cloned_but_not_installed_or_executed(self):
        stack = OpenSourceStack.default()

        for component in stack.components:
            self.assertTrue(Path(component.local_path).exists(), component.local_path)
            self.assertFalse(component.installed)
            self.assertFalse(component.executed)

    def test_workflow_exposes_open_source_stack(self):
        workflow = CaseWorkflow.demo()

        self.assertEqual(workflow.open_source_stack.component("langgraph").role, "workflow_orchestration")
        self.assertEqual(workflow.open_source_stack.component("agent-wiz").role, "security_review")


if __name__ == "__main__":
    unittest.main()
