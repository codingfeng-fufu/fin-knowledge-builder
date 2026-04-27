from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from .query_rewrite import QueryRewrite, rewrite_retrieval_query
from .rule_graph_rag import RuleGraphRagResult, RuleRagPassage


DEFAULT_DENSE_TOP_K = 10
_WORKER_SCRIPT = Path(__file__).with_name("dense_worker.py")


@dataclass(slots=True)
class DenseCandidate:
    rule_id: str
    score: float
    hits: int
    top_passage_id: str
    top_passage_type: str
    matched_rewrite_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "score": self.score,
            "hits": self.hits,
            "top_passage_id": self.top_passage_id,
            "top_passage_type": self.top_passage_type,
            "matched_rewrite_ids": list(self.matched_rewrite_ids),
        }


@dataclass(slots=True)
class DenseRetrievalResult:
    candidates: list[DenseCandidate]
    rewrites: list[QueryRewrite]
    metadata_by_rule_id: dict[str, dict[str, Any]]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "rewrites": [rewrite.to_dict() for rewrite in self.rewrites],
            "metadata_by_rule_id": {key: dict(value) for key, value in self.metadata_by_rule_id.items()},
            "diagnostics": dict(self.diagnostics),
        }


def dense_retrieval_available() -> bool:
    return _WORKER_SCRIPT.exists()


def retrieve_dense_candidates(
    *,
    artifact_root: str | Path,
    passages: list[RuleRagPassage],
    query,
    top_k: int = DEFAULT_DENSE_TOP_K,
) -> DenseRetrievalResult:
    rewrites = rewrite_retrieval_query(query, max_rewrites=4)
    if not rewrites or not dense_retrieval_available():
        return DenseRetrievalResult(candidates=[], rewrites=rewrites, metadata_by_rule_id={}, diagnostics={})

    payload = {
        "artifact_root": str(Path(artifact_root).resolve()),
        "top_k": top_k,
        "rewrites": [rewrite.to_dict() for rewrite in rewrites],
        "passages": [passage.to_dict() for passage in passages],
    }
    try:
        result = subprocess.run(
            ["python3", str(_WORKER_SCRIPT)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except Exception:
        return DenseRetrievalResult(candidates=[], rewrites=rewrites, metadata_by_rule_id={}, diagnostics={})

    try:
        data = json.loads(result.stdout)
    except Exception:
        return DenseRetrievalResult(candidates=[], rewrites=rewrites, metadata_by_rule_id={}, diagnostics={})

    candidates = [
        DenseCandidate(
            rule_id=str(item.get("rule_id", "")),
            score=float(item.get("score", 0.0) or 0.0),
            hits=int(item.get("hits", 0) or 0),
            top_passage_id=str(item.get("top_passage_id", "")),
            top_passage_type=str(item.get("top_passage_type", "")),
            matched_rewrite_ids=[str(rewrite_id) for rewrite_id in item.get("matched_rewrite_ids", [])],
        )
        for item in data.get("candidates", [])
        if item.get("rule_id")
    ]
    metadata_by_rule_id = {
        str(key): dict(value)
        for key, value in data.get("metadata_by_rule_id", {}).items()
    }
    return DenseRetrievalResult(
        candidates=candidates,
        rewrites=rewrites,
        metadata_by_rule_id=metadata_by_rule_id,
        diagnostics=dict(data.get("diagnostics", {})),
    )


def rerank_hybrid_matches(
    matches,
    *,
    dense_result: DenseRetrievalResult | None = None,
    graph_rag_result: RuleGraphRagResult | None = None,
    route=None,
):
    dense_metadata = {} if dense_result is None else dense_result.metadata_by_rule_id
    rag_metadata = {} if graph_rag_result is None else graph_rag_result.metadata_by_rule_id
    route_metadata = {} if route is None else route.route_metadata_by_rule_id

    def rerank_score(match) -> tuple[float, int, int]:
        rule_id = match.record.rule_id
        score = float(match.score_total)
        dense_score = float(dense_metadata.get(rule_id, {}).get("dense_score", 0.0))
        dense_hits = int(dense_metadata.get(rule_id, {}).get("dense_hits", 0))
        graph_rag_hits = int(rag_metadata.get(rule_id, {}).get("graph_rag_hits", 0))
        graph_route_score = int(route_metadata.get(rule_id, {}).get("community_score", 0))
        score += dense_score * 20.0
        score += dense_hits * 4.0
        score += graph_rag_hits * 2.0
        score += graph_route_score * 0.15
        return score, dense_hits, graph_rag_hits

    return sorted(
        matches,
        key=lambda match: (
            rerank_score(match)[0],
            match.eligible_for_direct_match,
            match.eligible_for_composition,
            match.signal_hits,
        ),
        reverse=True,
    )
