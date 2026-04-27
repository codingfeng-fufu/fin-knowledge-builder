from __future__ import annotations

from collections import Counter
import hashlib
import math
import os
from typing import Any
from typing import Iterable

import numpy as np

from .hybrid_retrieval_types import tokenize_text

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity
except Exception:  # pragma: no cover - fallback path
    TfidfVectorizer = None
    sklearn_cosine_similarity = None

try:
    import torch
except Exception:  # pragma: no cover - fallback path
    torch = None


def _patch_torch_pytree() -> None:
    if torch is None:
        return
    try:
        import torch.utils._pytree as pytree
    except Exception:  # pragma: no cover
        return
    if hasattr(pytree, "register_pytree_node"):
        return
    if not hasattr(pytree, "_register_pytree_node"):
        return

    def _compat_register(*args, **kwargs):
        kwargs.pop("serialized_type_name", None)
        return pytree._register_pytree_node(*args, **kwargs)

    pytree.register_pytree_node = _compat_register


def _load_transformer_stack() -> tuple[Any | None, Any | None, str | None]:
    if torch is None:
        return None, None, "torch is not available"
    try:
        _patch_torch_pytree()
        from transformers import AutoModel, AutoTokenizer
        return AutoTokenizer, AutoModel, None
    except Exception as exc:  # pragma: no cover - environment dependent
        return None, None, f"{type(exc).__name__}: {exc}"


def _probe_local_transformer_model(
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
) -> str | None:
    tokenizer_cls, model_cls, error = _load_transformer_stack()
    if tokenizer_cls is None or model_cls is None:
        return error or "transformer stack unavailable"
    try:
        tokenizer_cls.from_pretrained(model_name, local_files_only=True)
        model_cls.from_pretrained(model_name, local_files_only=True)
        return None
    except Exception as exc:  # pragma: no cover - environment dependent
        return f"{type(exc).__name__}: {exc}"


def _char_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> Counter[str]:
    compact = "".join(ch.lower() for ch in text if not ch.isspace())
    counts: Counter[str] = Counter()
    for n in range(min_n, max_n + 1):
        if len(compact) < n:
            continue
        for index in range(len(compact) - n + 1):
            counts[compact[index:index + n]] += 1
    return counts


def _counter_cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _dice_similarity(left_terms: set[str], right_terms: set[str]) -> float:
    if not left_terms or not right_terms:
        return 0.0
    overlap = len(left_terms & right_terms)
    return (2 * overlap) / (len(left_terms) + len(right_terms))


class EmbeddingBackend:
    backend_id = "base"
    device = "cpu"

    def similarity_matrix(self, query_texts: list[str], candidate_texts: list[str]) -> np.ndarray:
        raise NotImplementedError


class SklearnCharNgramEmbeddingBackend(EmbeddingBackend):
    backend_id = "sklearn_char_ngram"

    def __init__(self, ngram_range: tuple[int, int] = (2, 4)) -> None:
        if TfidfVectorizer is None or sklearn_cosine_similarity is None:
            raise RuntimeError("sklearn is not available")
        self.ngram_range = ngram_range

    def similarity_matrix(self, query_texts: list[str], candidate_texts: list[str]) -> np.ndarray:
        if not query_texts or not candidate_texts:
            return np.zeros((len(query_texts), len(candidate_texts)), dtype=np.float32)
        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=self.ngram_range,
            lowercase=True,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform([*query_texts, *candidate_texts])
        query_matrix = matrix[: len(query_texts)]
        candidate_matrix = matrix[len(query_texts) :]
        return sklearn_cosine_similarity(query_matrix, candidate_matrix).astype(np.float32)


class HeuristicEmbeddingBackend(EmbeddingBackend):
    backend_id = "heuristic_char_term"

    def similarity_matrix(self, query_texts: list[str], candidate_texts: list[str]) -> np.ndarray:
        if not query_texts or not candidate_texts:
            return np.zeros((len(query_texts), len(candidate_texts)), dtype=np.float32)
        rows: list[list[float]] = []
        for query_text in query_texts:
            query_terms = tokenize_text(query_text)
            query_ngrams = _char_ngrams(query_text)
            row: list[float] = []
            for candidate_text in candidate_texts:
                candidate_terms = tokenize_text(candidate_text)
                char_score = _counter_cosine(query_ngrams, _char_ngrams(candidate_text))
                term_score = _dice_similarity(query_terms, candidate_terms)
                row.append(round(char_score * 0.65 + term_score * 0.35, 4))
            rows.append(row)
        return np.array(rows, dtype=np.float32)


def _stable_bucket(token: str, dim: int) -> tuple[int, int]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little", signed=False)
    index = value % dim
    sign = -1 if ((value >> 8) & 1) else 1
    return index, sign


class TorchHashEmbeddingBackend(EmbeddingBackend):
    backend_id = "torch_hash"

    def __init__(self, *, device: str = "cpu", dim: int = 2048, ngram_range: tuple[int, int] = (2, 4)) -> None:
        if torch is None:
            raise RuntimeError("torch is not available")
        self.device = _resolve_device(device)
        self.dim = dim
        self.ngram_range = ngram_range

    def _encode(self, texts: list[str]):
        matrix = torch.zeros((len(texts), self.dim), dtype=torch.float32, device=self.device)
        for row, text in enumerate(texts):
            counts = _char_ngrams(text, min_n=self.ngram_range[0], max_n=self.ngram_range[1])
            if not counts:
                continue
            for token, value in counts.items():
                index, sign = _stable_bucket(token, self.dim)
                matrix[row, index] += float(value * sign)
            norm = torch.linalg.vector_norm(matrix[row], ord=2)
            if float(norm) > 0.0:
                matrix[row] = matrix[row] / norm
        return matrix

    def similarity_matrix(self, query_texts: list[str], candidate_texts: list[str]) -> np.ndarray:
        if not query_texts or not candidate_texts:
            return np.zeros((len(query_texts), len(candidate_texts)), dtype=np.float32)
        query_matrix = self._encode(query_texts)
        candidate_matrix = self._encode(candidate_texts)
        similarity = torch.matmul(query_matrix, candidate_matrix.transpose(0, 1))
        try:
            return similarity.detach().cpu().numpy().astype(np.float32)
        except Exception:
            return np.array(similarity.detach().cpu().float().tolist(), dtype=np.float32)


class TransformerModelEmbeddingBackend(EmbeddingBackend):
    backend_id = "transformer_model"

    def __init__(
        self,
        *,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device: str = "cpu",
        max_length: int = 256,
    ) -> None:
        tokenizer_cls, model_cls, error = _load_transformer_stack()
        if tokenizer_cls is None or model_cls is None:
            raise RuntimeError(f"transformer backend unavailable: {error}")
        if torch is None:
            raise RuntimeError("torch is not available")
        self.device = _resolve_device(device)
        self.model_name = model_name
        self.max_length = max_length
        try:
            self.tokenizer = tokenizer_cls.from_pretrained(model_name, local_files_only=True)
            self.model = model_cls.from_pretrained(model_name, local_files_only=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(f"transformer model backend unavailable: {type(exc).__name__}: {exc}") from exc
        self.model.to(self.device)
        self.model.eval()

    def _encode(self, texts: list[str]):
        if torch is None:
            raise RuntimeError("torch is not available")
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.no_grad():
            outputs = self.model(**encoded)
        hidden = outputs.last_hidden_state
        attention_mask = encoded["attention_mask"].unsqueeze(-1)
        masked = hidden * attention_mask
        pooled = masked.sum(dim=1) / attention_mask.sum(dim=1).clamp(min=1)
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return pooled

    def similarity_matrix(self, query_texts: list[str], candidate_texts: list[str]) -> np.ndarray:
        if not query_texts or not candidate_texts:
            return np.zeros((len(query_texts), len(candidate_texts)), dtype=np.float32)
        query_matrix = self._encode(query_texts)
        candidate_matrix = self._encode(candidate_texts)
        similarity = torch.matmul(query_matrix, candidate_matrix.transpose(0, 1))
        try:
            return similarity.detach().cpu().numpy().astype(np.float32)
        except Exception:
            return np.array(similarity.detach().cpu().float().tolist(), dtype=np.float32)


def _cuda_available() -> bool:
    return bool(torch is not None and torch.cuda.is_available())


def _resolve_device(requested_device: str | None) -> str:
    if requested_device in (None, "", "auto"):
        return "cuda" if _cuda_available() else "cpu"
    if requested_device == "cuda" and not _cuda_available():
        return "cpu"
    return requested_device


def available_embedding_backends() -> dict[str, dict[str, object]]:
    tokenizer_cls, model_cls, transformer_error = _load_transformer_stack()
    transformer_model_error = _probe_local_transformer_model()
    return {
        "sklearn_char_ngram": {
            "available": bool(TfidfVectorizer is not None and sklearn_cosine_similarity is not None),
            "devices": ["cpu"],
        },
        "torch_hash": {
            "available": bool(torch is not None),
            "devices": ["cpu", "cuda"] if _cuda_available() else ["cpu"],
        },
        "heuristic_char_term": {
            "available": True,
            "devices": ["cpu"],
        },
        "transformer_model": {
            "available": bool(tokenizer_cls is not None and model_cls is not None and transformer_model_error is None),
            "devices": ["cpu", "cuda"] if _cuda_available() else ["cpu"],
            "default_model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "stack_error": transformer_error,
            "error": transformer_model_error,
        },
    }


def make_embedding_backend(
    backend_id: str | None = None,
    *,
    device: str | None = None,
    model_name: str | None = None,
) -> EmbeddingBackend:
    selected_backend = backend_id or os.getenv("PHASE1_EMBED_BACKEND") or "auto"
    selected_device = device or os.getenv("PHASE1_EMBED_DEVICE") or "auto"
    selected_model_name = model_name or os.getenv("PHASE1_EMBED_MODEL") or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    if selected_backend == "auto":
        if TfidfVectorizer is not None and sklearn_cosine_similarity is not None:
            return SklearnCharNgramEmbeddingBackend()
        if torch is not None:
            return TorchHashEmbeddingBackend(device="cpu")
        return HeuristicEmbeddingBackend()

    if selected_backend == "transformer_model":
        return TransformerModelEmbeddingBackend(device=selected_device, model_name=selected_model_name)
    if selected_backend == "torch_hash":
        return TorchHashEmbeddingBackend(device=selected_device)
    if selected_backend == "sklearn_char_ngram":
        return SklearnCharNgramEmbeddingBackend()
    if selected_backend == "heuristic_char_term":
        return HeuristicEmbeddingBackend()
    raise ValueError(f"unsupported embedding backend: {selected_backend}")


def default_embedding_backend() -> EmbeddingBackend:
    return make_embedding_backend()


def semantic_similarity_matrix(
    query_texts: list[str],
    candidate_texts: list[str],
    *,
    backend: EmbeddingBackend | None = None,
) -> np.ndarray:
    active_backend = default_embedding_backend() if backend is None else backend
    return active_backend.similarity_matrix(query_texts, candidate_texts)


def semantic_similarity_score(
    query_text: str,
    candidate_text: str,
    *,
    backend: EmbeddingBackend | None = None,
) -> float:
    matrix = semantic_similarity_matrix([query_text], [candidate_text], backend=backend)
    if matrix.size == 0:
        return 0.0
    return float(round(float(matrix[0, 0]), 4))
