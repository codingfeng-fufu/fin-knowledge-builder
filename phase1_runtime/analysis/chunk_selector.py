"""
BM25-lite chunk selector.

Scores document chunks against an extraction goal + hint keywords and
returns the top-k most relevant chunks.  Designed for Chinese + English
mixed text; uses character-level n-grams (bigrams) plus whole-token
matching so no external tokenizer is needed.
"""
from __future__ import annotations

import math
import re
from typing import Any


def _tokenize(text: str) -> list[str]:
    """Extract tokens: ASCII words + Chinese character bigrams."""
    tokens: list[str] = []
    # ASCII words (numbers, latin letters)
    tokens.extend(w.lower() for w in re.findall(r"[A-Za-z0-9]+", text))
    # Chinese characters — keep individual chars AND bigrams
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(cjk)
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])
    return tokens


def _build_query_terms(goal: str, hints: list[str]) -> dict[str, float]:
    """Build weighted query term dict.  Hints get 2x weight."""
    terms: dict[str, float] = {}
    for t in _tokenize(goal):
        terms[t] = terms.get(t, 0) + 1.0
    for hint in hints:
        for t in _tokenize(hint):
            terms[t] = terms.get(t, 0) + 2.0  # hints are more specific
    return terms


def _bm25_score(
    query_terms: dict[str, float],
    chunk_tokens: list[str],
    avg_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Approximate BM25 score (IDF approximated as uniform = 1)."""
    tf_map: dict[str, int] = {}
    for t in chunk_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1

    dl = len(chunk_tokens) or 1
    score = 0.0
    for term, weight in query_terms.items():
        tf = tf_map.get(term, 0)
        if tf == 0:
            continue
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * dl / avg_len)
        score += weight * (numerator / denominator)
    return score


def select_top_k_chunks(
    chunks: list[dict[str, Any]],
    goal: str,
    hints: list[str] | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    Return the top-k chunks most relevant to *goal* + *hints*.

    If len(chunks) <= top_k, returns all chunks unchanged.
    Chunks with zero score are excluded unless that would leave fewer
    than min(3, top_k) results.
    """
    if not chunks:
        return []
    if len(chunks) <= top_k:
        return chunks

    query_terms = _build_query_terms(goal, hints or [])
    if not query_terms:
        return chunks[:top_k]

    tokenized = [_tokenize(c.get("text", "")) for c in chunks]
    avg_len = sum(len(t) for t in tokenized) / len(tokenized) or 1.0

    scored = [
        (i, _bm25_score(query_terms, tok, avg_len))
        for i, tok in enumerate(tokenized)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Take top_k; if all top-k have zero score, fall back to original order
    selected = scored[:top_k]
    if all(s == 0 for _, s in selected):
        return chunks[:top_k]

    # Preserve original document order for coherence
    top_indices = sorted(i for i, _ in selected)
    return [chunks[i] for i in top_indices]
