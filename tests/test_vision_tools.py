import base64
import tempfile
import unittest
from pathlib import Path

from case_agent_demo.config import ModelProfile
from case_agent_demo.models import Material, MaterialType
from case_agent_demo.vision_tools import (
    ImageEvidenceDescription,
    QwenImageEvidenceTool,
    local_image_to_data_url,
)


class FakeQwenClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.payloads = []

    def build_vision_payload(self, profile, prompt, image_url):
        payload = {
            "model": profile.model_name,
            "messages": [{"content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_url}}]}],
        }
        self.payloads.append(payload)
        return payload

    def chat_completions(self, payload):
        return {"choices": [{"message": {"content": self.content}}]}


class VisionToolsTests(unittest.TestCase):
    def test_local_image_to_data_url_uses_file_mime_and_base64(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "evidence.png"
            image_path.write_bytes(b"fake-png-bytes")

            data_url = local_image_to_data_url(image_path)

            self.assertTrue(data_url.startswith("data:image/png;base64,"))
            encoded = data_url.split(",", 1)[1]
            self.assertEqual(base64.b64decode(encoded), b"fake-png-bytes")

    def test_qwen_image_evidence_tool_parses_json_content(self):
        client = FakeQwenClient('{"pic":"现场照片显示门锁损坏","text":"签名：张三","confidence":0.91}')
        profile = ModelProfile("vision", "qwen", "qwen-vl-plus", 0.0, "vision")
        tool = QwenImageEvidenceTool(client=client, profile=profile, prompt="只输出 JSON。")
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "evidence.jpg"
            image_path.write_bytes(b"fake-jpg-bytes")
            material = Material("P1", MaterialType.EVIDENCE_IMAGE, "", source_path=str(image_path))

            description = tool.describe(material)

        self.assertEqual(description.pic, "现场照片显示门锁损坏")
        self.assertEqual(description.text, "签名：张三")
        self.assertEqual(description.confidence, 0.91)
        image_url = client.payloads[0]["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))

    def test_qwen_image_evidence_tool_marks_low_confidence_for_human_input(self):
        description = ImageEvidenceDescription(pic="看不清", text="", confidence=0.5)

        self.assertTrue(description.needs_human_input)


if __name__ == "__main__":
    unittest.main()
