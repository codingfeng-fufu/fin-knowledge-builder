"""Unit tests for chunk_selector.select_top_k_chunks."""
from __future__ import annotations

import unittest

from phase1_runtime.analysis.chunk_selector import select_top_k_chunks, _tokenize


class ChunkSelectorTests(unittest.TestCase):

    def _make_chunks(self, texts: list[str]) -> list[dict]:
        return [{"chunk_id": f"c{i}", "text": t, "locator": {"line": i}} for i, t in enumerate(texts)]

    def test_returns_all_when_fewer_than_top_k(self):
        chunks = self._make_chunks(["abc", "def"])
        result = select_top_k_chunks(chunks, goal="abc", top_k=10)
        self.assertEqual(len(result), 2)

    def test_top_k_limits_output(self):
        chunks = self._make_chunks([f"chunk {i}" for i in range(20)])
        result = select_top_k_chunks(chunks, goal="chunk 5", top_k=5)
        self.assertLessEqual(len(result), 5)

    def test_relevant_chunk_ranked_high(self):
        chunks = self._make_chunks([
            "这是一段无关文本，讲述天气情况。",
            "贷款距离到期还有20天，借款人需要注意。",
            "合同签署日期为2023年1月。",
            "公司名称：ABC有限公司。",
            "到期日临近，剩余天数为15天。",
        ])
        result = select_top_k_chunks(
            chunks,
            goal="从文档中找到贷款距离到期还有多少天",
            hints=["到期", "天", "剩余", "距离到期"],
            top_k=2,
        )
        texts = [c["text"] for c in result]
        # At least one relevant chunk about maturity days should be selected
        self.assertTrue(any("到期" in t or "天" in t for t in texts))

    def test_preserves_original_order(self):
        chunks = self._make_chunks([
            "净值0.85，高于警戒线。",
            "无关文本。",
            "当前单位净值为0.72，低于阈值0.80。",
        ])
        result = select_top_k_chunks(
            chunks,
            goal="找到当前净值",
            hints=["净值", "NAV"],
            top_k=2,
        )
        # Selected chunks should maintain original document order
        indices = [chunks.index(c) for c in result]
        self.assertEqual(indices, sorted(indices))

    def test_empty_chunks(self):
        result = select_top_k_chunks([], goal="anything", top_k=5)
        self.assertEqual(result, [])

    def test_tokenize_mixed(self):
        tokens = _tokenize("NAV净值0.72")
        self.assertIn("nav", tokens)
        self.assertIn("净", tokens)
        self.assertIn("值", tokens)
        self.assertIn("净值", tokens)
        self.assertIn("0", tokens)

    def test_hint_weight_boosts_relevant_chunk(self):
        # Chunk with hint keyword should beat longer chunk without it
        chunks = self._make_chunks([
            "a " * 50 + "irrelevant content",
            "净值 threshold warning",
        ])
        result = select_top_k_chunks(
            chunks,
            goal="找到净值",
            hints=["净值"],
            top_k=1,
        )
        self.assertIn("净值", result[0]["text"])


if __name__ == "__main__":
    unittest.main()
