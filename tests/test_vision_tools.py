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

    def build_vision_group_payload(self, profile, prompt, image_urls):
        content = [{"type": "text", "text": prompt}]
        content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in image_urls)
        payload = {"model": profile.model_name, "messages": [{"content": content}]}
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

    def test_local_image_to_data_url_rejects_non_image_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.docx"
            path.write_bytes(b"not an image")

            with self.assertRaises(ValueError) as context:
                local_image_to_data_url(path)

        self.assertIn("Unsupported image file", str(context.exception))
        self.assertIn("report.docx", str(context.exception))

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


    def test_qwen_image_evidence_tool_describes_each_image_group_in_isolated_payload(self):
        client = FakeQwenClient('{"pic":"group description","text":"group text","confidence":0.95}')
        profile = ModelProfile("vision", "qwen", "qwen-vl-plus", 0.0, "vision")
        tool = QwenImageEvidenceTool(client=client, profile=profile, prompt="json only")
        with tempfile.TemporaryDirectory() as tmp:
            group_a = Path(tmp) / "group_a"
            group_b = Path(tmp) / "group_b"
            group_a.mkdir()
            group_b.mkdir()
            a1 = group_a / "1.jpg"
            a2 = group_a / "2.jpg"
            b1 = group_b / "1.jpg"
            for path in (a1, a2, b1):
                path.write_bytes(path.name.encode("utf-8"))

            description = tool.describe_group("group_a", [str(a1), str(a2)])

        self.assertEqual(description.pic, "group description")
        content = client.payloads[0]["messages"][0]["content"]
        image_urls = [item["image_url"]["url"] for item in content if item["type"] == "image_url"]
        self.assertEqual(len(image_urls), 2)
        self.assertTrue(all(url.startswith("data:image/jpeg;base64,") for url in image_urls))
        self.assertNotIn(str(b1), str(client.payloads[0]))


if __name__ == "__main__":
    unittest.main()
