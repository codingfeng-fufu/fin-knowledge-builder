"""
Case-based retrieval for M4.

Searches historical workspace runs by BM25 similarity on question_text,
filtered by scenario_id.  Results can be used to:
  - Shortcut execution when a near-identical case exists (score > HIGH_THRESHOLD)
  - Provide context for the current run
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..factory.rule_factory_store import DEFAULT_DB_PATH, list_workspace_run_records


# ── tokeniser (same logic as chunk_selector, kept local to avoid circular import) ──

def _tok(text: str) -> list[str]:
    tokens: list[str] = []
    tokens.extend(w.lower() for w in re.findall(r"[A-Za-z0-9]+", text))
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(cjk)
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])
    return tokens


def _bm25(query_terms: list[str], doc_tokens: list[str], avg_len: float,
          k1: float = 1.5, b: float = 0.75) -> float:
    tf_map: dict[str, int] = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1
    dl = len(doc_tokens) or 1
    score = 0.0
    for term in query_terms:
        tf = tf_map.get(term, 0)
        if tf == 0:
            continue
        score += (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_len))
    return score


# ── public API ──

@dataclass(slots=True)
class CaseMatch:
    workspace_run_id: str
    case_id: str | None
    scenario_id: str
    question_text: str
    final_decision: str | None
    route_decision: str | None
    score: float
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_run_id": self.workspace_run_id,
            "case_id": self.case_id,
            "scenario_id": self.scenario_id,
            "question_text": self.question_text,
            "final_decision": self.final_decision,
            "route_decision": self.route_decision,
            "score": round(self.score, 4),
            "created_at": self.created_at,
        }


_HIGH_SIMILARITY = 0.80   # shortcut threshold
_LOW_SIMILARITY  = 0.10   # minimum to include as context


def retrieve_similar_cases(
    question_text: str,
    scenario_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    top_k: int = 3,
) -> list[CaseMatch]:
    """
    Return top-k historical workspace runs for *scenario_id* ordered by
    BM25 similarity to *question_text*.  Only cases with status='completed'
    and score >= _LOW_SIMILARITY are returned.
    """
    records = list_workspace_run_records(db_path=db_path)
    candidates = [r for r in records if r.get("scenario_id") == scenario_id
                  and r.get("status") == "completed"]
    if not candidates:
        return []

    query_tokens = _tok(question_text)
    if not query_tokens:
        return []

    tokenized = [_tok(r["question_text"]) for r in candidates]
    avg_len = sum(len(t) for t in tokenized) / len(tokenized) or 1.0

    scored: list[tuple[float, dict]] = []
    for rec, tok in zip(candidates, tokenized):
        s = _bm25(query_tokens, tok, avg_len)
        if s >= _LOW_SIMILARITY:
            scored.append((s, rec))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        CaseMatch(
            workspace_run_id=rec["workspace_run_id"],
            case_id=rec.get("case_id"),
            scenario_id=rec["scenario_id"],
            question_text=rec["question_text"],
            final_decision=rec.get("final_decision"),
            route_decision=rec.get("route_decision"),
            score=score,
            created_at=rec.get("created_at", ""),
        )
        for score, rec in scored[:top_k]
    ]


def should_shortcut(matches: list[CaseMatch]) -> CaseMatch | None:
    """
    Return the top match if it exceeds the HIGH_SIMILARITY threshold
    and has a definitive final_decision.  Otherwise return None.
    """
    if not matches:
        return None
    top = matches[0]
    if top.score >= _HIGH_SIMILARITY and top.final_decision:
        return top
    return None
