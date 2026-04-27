from __future__ import annotations

from typing import Iterable

from .embedding_backend import semantic_similarity_score
from .hybrid_retrieval_types import tokenize_text


def semantic_similarity(
    query_text: str,
    asset_text: str,
    *,
    query_terms: Iterable[str] | None = None,
    asset_terms: Iterable[str] | None = None,
) -> float:
    backend_score = semantic_similarity_score(query_text, asset_text)
    query_term_set = set(query_terms) if query_terms is not None else tokenize_text(query_text)
    asset_term_set = set(asset_terms) if asset_terms is not None else tokenize_text(asset_text)
    overlap = 0.0
    if query_term_set and asset_term_set:
        overlap = (2 * len(query_term_set & asset_term_set)) / (len(query_term_set) + len(asset_term_set))
    return round(backend_score * 0.8 + overlap * 0.2, 4)
