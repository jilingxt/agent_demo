from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from case_agent_demo.legal_kb_cli import main


class LegalKbCliTests(unittest.TestCase):
    def test_ingest_stats_and_search_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "laws"
            source.mkdir()
            (source / "law.md").write_text(
                "示例法\n第一条 盗窃他人财物的，依法处理。",
                encoding="utf-8",
            )
            root = Path(tmp) / "kb"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "--root",
                            str(root),
                            "ingest",
                            "--source",
                            str(source),
                            "--embedding-provider",
                            "hashing",
                        ]
                    ),
                    0,
                )
                self.assertEqual(main(["--root", str(root), "stats"]), 0)
                self.assertEqual(main(["--root", str(root), "search", "盗窃财物"]), 0)

            self.assertIn('"documents": 1', output.getvalue())
            self.assertIn('"article": "第一条"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
