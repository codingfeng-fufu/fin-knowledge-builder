from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).resolve().parent / "scripts" / "read_pdf.py"
MODULE_NAME = "claude_style_pdf_reader_test_module"

spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[MODULE_NAME] = module
spec.loader.exec_module(module)


class ExtractJSONObjectTests(unittest.TestCase):
    def test_extracts_plain_json(self) -> None:
        parsed = module.extract_json_object('{"title":"X","methods":[]}')
        self.assertEqual(parsed["title"], "X")

    def test_extracts_fenced_json(self) -> None:
        parsed = module.extract_json_object("```json\n{\"title\":\"Y\",\"methods\":[]}\n```")
        self.assertEqual(parsed["title"], "Y")


class BuildPluginOutputTests(unittest.TestCase):
    def test_builds_versioned_plugin_schema(self) -> None:
        args = SimpleNamespace(
            pdf_path=Path("paper.pdf"),
            pages=None,
            auto_pages=False,
            auto_batch_size=5,
            force_file_extract=False,
        )
        result = {
            "mode": "file_extract",
            "text": "analysis text",
            "claudeCompatibleRouting": {
                "claudeRoute": "document_block",
                "transport": "moonshot_file_extract_shim",
                "inspection": {
                    "pageCount": 3,
                    "fileSize": 1234,
                },
            },
            "response": {
                "usage": {
                    "total_tokens": 10,
                }
            },
            "file": {
                "id": "file-123",
            },
        }

        output = module.build_plugin_output(args, result)

        self.assertEqual(output["plugin"], module.PLUGIN_NAME)
        self.assertEqual(output["schemaVersion"], module.PLUGIN_SCHEMA_VERSION)
        self.assertEqual(output["document"]["pageCount"], 3)
        self.assertEqual(output["analysis"]["usage"]["total_tokens"], 10)
        self.assertEqual(output["analysis"]["file"]["id"], "file-123")


class BuildSummaryJsonOutputTests(unittest.TestCase):
    def test_builds_minimal_summary_schema(self) -> None:
        args = SimpleNamespace()
        plugin_output = {
            "mode": "auto_pages_aggregate",
            "document": {
                "pdfPath": "paper.pdf",
                "pageCount": 13,
                "fileSizeBytes": 1234,
            },
            "routing": {
                "claudeRoute": "auto_pages_aggregate",
            },
            "analysis": {
                "usage": {
                    "total_tokens": 99,
                }
            },
        }
        structured = {
            "title": "Paper",
            "oneSentenceSummary": "One sentence.",
            "researchProblem": "Problem.",
            "methods": ["Method A"],
            "experiments": ["Dataset X"],
            "results": ["Result Y"],
            "conclusions": ["Conclusion Z"],
            "limitations": ["Limitation Q"],
            "evidenceScope": "Pages 1-13",
        }

        output = module.build_summary_json_output(args, plugin_output, structured)

        self.assertEqual(output["outputMode"], "summary-json")
        self.assertEqual(output["schemaVersion"], module.SUMMARY_SCHEMA_VERSION)
        self.assertEqual(output["summary"]["title"], "Paper")
        self.assertEqual(output["usage"]["total_tokens"], 99)


if __name__ == "__main__":
    unittest.main()
