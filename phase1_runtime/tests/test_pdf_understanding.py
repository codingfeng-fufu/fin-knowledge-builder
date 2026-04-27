from __future__ import annotations

import unittest

from phase1_runtime.parsing.pdf_understanding import _select_pages_from_texts


class PdfUnderstandingTests(unittest.TestCase):
    def test_select_pages_from_texts_prefers_query_relevant_pages(self) -> None:
        selected, metadata = _select_pages_from_texts(
            [
                "证券研究报告 工商银行 增持 评级",
                "行业背景与宏观讨论",
                "主要下行风险与目标价估值",
                "免责声明",
            ],
            query_text="这份研报对工商银行的投资评级是什么？",
        )
        self.assertIn(1, selected)
        self.assertEqual(metadata["mode"], "query_ranked")
        self.assertLessEqual(len(selected), metadata["page_budget"])

    def test_select_pages_from_texts_falls_back_to_first_pages_when_no_match(self) -> None:
        selected, metadata = _select_pages_from_texts(
            [
                "",
                "",
                "",
                "",
            ],
            query_text="这份研报对工商银行的投资评级是什么？",
        )
        self.assertEqual(selected[0], 1)
        self.assertEqual(metadata["mode"], "fallback_first_pages")


if __name__ == "__main__":
    unittest.main()
