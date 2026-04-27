from __future__ import annotations

import unittest

from phase1_runtime.retrieval.embedding_backend import (
    available_embedding_backends,
    default_embedding_backend,
    make_embedding_backend,
    semantic_similarity_matrix,
    semantic_similarity_score,
)


class EmbeddingBackendTests(unittest.TestCase):
    def test_default_backend_is_available(self) -> None:
        backend = default_embedding_backend()
        self.assertIn(backend.backend_id, {"sklearn_char_ngram", "torch_hash", "heuristic_char_term"})

    def test_available_backends_reports_torch_hash(self) -> None:
        payload = available_embedding_backends()
        self.assertIn("torch_hash", payload)
        self.assertTrue(payload["torch_hash"]["available"])
        self.assertIn("transformer_model", payload)
        self.assertIn("available", payload["transformer_model"])

    def test_make_torch_hash_backend_cpu(self) -> None:
        backend = make_embedding_backend("torch_hash", device="cpu")
        self.assertEqual(backend.backend_id, "torch_hash")
        self.assertEqual(backend.device, "cpu")

    def test_make_torch_hash_backend_cuda_falls_back_when_unavailable(self) -> None:
        backend = make_embedding_backend("torch_hash", device="cuda")
        self.assertEqual(backend.backend_id, "torch_hash")
        self.assertIn(backend.device, {"cpu", "cuda"})

    def test_transformer_backend_reports_unavailable_or_raises_runtime(self) -> None:
        payload = available_embedding_backends()["transformer_model"]
        if payload["available"]:
            backend = make_embedding_backend("transformer_model", device="cpu")
            self.assertEqual(backend.backend_id, "transformer_model")
            self.assertEqual(backend.device, "cpu")
            return
        with self.assertRaises(RuntimeError):
            make_embedding_backend("transformer_model", device="cpu")

    def test_similarity_matrix_prefers_related_text(self) -> None:
        matrix = semantic_similarity_matrix(
            ["某私募产品单位份额价格触发合同警戒线后，管理人是否要向持有人做提示？"],
            [
                "适用于私募产品净值跌破合同阈值后是否需要向投资者提示风险的判断。",
                "适用于贷款展期是否需要向借款人发送通知的判断。",
            ],
        )
        self.assertEqual(matrix.shape, (1, 2))
        self.assertGreater(float(matrix[0, 0]), float(matrix[0, 1]))

    def test_similarity_score_for_identical_text_is_high(self) -> None:
        score = semantic_similarity_score(
            "适用于私募产品净值跌破合同阈值后是否需要向投资者提示风险的判断。",
            "适用于私募产品净值跌破合同阈值后是否需要向投资者提示风险的判断。",
        )
        self.assertGreater(score, 0.9)

    def test_torch_hash_backend_prefers_related_text(self) -> None:
        backend = make_embedding_backend("torch_hash", device="cpu")
        matrix = semantic_similarity_matrix(
            ["某私募产品单位份额价格触发合同警戒线后，管理人是否要向持有人做提示？"],
            [
                "适用于私募产品净值跌破合同阈值后是否需要向投资者提示风险的判断。",
                "适用于贷款展期是否需要向借款人发送通知的判断。",
            ],
            backend=backend,
        )
        self.assertGreater(float(matrix[0, 0]), float(matrix[0, 1]))


if __name__ == "__main__":
    unittest.main()
