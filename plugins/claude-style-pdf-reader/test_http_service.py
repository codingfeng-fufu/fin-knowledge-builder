from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent / "scripts" / "http_service.py"
MODULE_NAME = "claude_style_pdf_reader_http_test_module"

spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[MODULE_NAME] = module
spec.loader.exec_module(module)


class RequestToArgvTests(unittest.TestCase):
    def test_builds_expected_argv(self) -> None:
        argv = module.request_to_argv(
            {
                "pdf_path": "paper.pdf",
                "output_mode": "summary-json",
                "auto_pages": True,
                "pretty": True,
                "max_tokens": 1234,
            }
        )
        self.assertEqual(
            argv,
            [
                "paper.pdf",
                "--max-tokens",
                "1234",
                "--output-mode",
                "summary-json",
                "--auto-pages",
                "--pretty",
            ],
        )

    def test_requires_pdf_path(self) -> None:
        with self.assertRaises(ValueError):
            module.request_to_argv({})


class BuildWrapperArgsForSessionTests(unittest.TestCase):
    def test_builds_namespace_from_session(self) -> None:
        session = {
            "pdfPath": "paper.pdf",
            "sessionType": "auto_pages",
            "autoBatchSize": 5,
            "apiKey": "sk-test",
            "baseUrl": "https://example.com/v1",
            "model": "kimi-k2.5",
            "maxTokens": 4096,
            "noImageOptimize": False,
            "pages": None,
        }
        args = module.build_wrapper_args_for_session(
            session,
            {"question": "What is the method?", "output_mode": "summary-json"},
        )
        self.assertTrue(args.auto_pages)
        self.assertEqual(args.output_mode, "summary-json")
        self.assertEqual(args.max_tokens, 4096)


if __name__ == "__main__":
    unittest.main()
