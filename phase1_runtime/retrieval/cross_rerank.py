from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from .rule_graph_rag import RuleRagPassage


_WORKER_SCRIPT = Path(__file__).with_name("cross_rerank_worker.py")


@dataclass(slots=True)
class CrossRerankCandidate:
    rule_id: str
    score: float
    candidate_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "score": self.score,
            "candidate_text": self.candidate_text,
        }


@dataclass(slots=True)
class CrossRerankResult:
    candidates: list[CrossRerankCandidate]
    metadata_by_rule_id: dict[str, dict[str, Any]]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "metadata_by_rule_id": {key: dict(value) for key, value in self.metadata_by_rule_id.items()},
            "diagnostics": dict(self.diagnostics),
        }


def cross_rerank_available() -> bool:
    return _WORKER_SCRIPT.exists()


def _build_candidate_text(rule_id: str, rag_catalog: list[RuleRagPassage]) -> str:
    priority = {
        "rule_overview": 0,
        "rule_inputs": 1,
        "rule_outputs": 2,
        "rule_composition": 3,
        "rule_steps": 4,
    }
    passages = [item for item in rag_catalog if item.rule_id == rule_id]
    passages.sort(key=lambda item: priority.get(item.passage_type, 99))
    chunks: list[str] = []
    for passage in passages[:4]:
        chunks.append(f"[{passage.passage_type}]\n{passage.text}")
    return "\n\n".join(chunks)


def cross_rerank_candidates(
    *,
    query_text: str,
    candidate_rule_ids: list[str],
    rag_catalog: list[RuleRagPassage],
    top_n: int = 8,
) -> CrossRerankResult:
    if not cross_rerank_available():
        return CrossRerankResult(candidates=[], metadata_by_rule_id={}, diagnostics={})

    payload_candidates = []
    for rule_id in candidate_rule_ids[:top_n]:
        candidate_text = _build_candidate_text(rule_id, rag_catalog)
        if not candidate_text:
            continue
        payload_candidates.append(
            {
                "rule_id": rule_id,
                "candidate_text": candidate_text,
            }
        )
    if not payload_candidates:
        return CrossRerankResult(candidates=[], metadata_by_rule_id={}, diagnostics={})

    payload = {
        "query_text": query_text,
        "candidates": payload_candidates,
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
        return CrossRerankResult(candidates=[], metadata_by_rule_id={}, diagnostics={})

    try:
        data = json.loads(result.stdout)
    except Exception:
        return CrossRerankResult(candidates=[], metadata_by_rule_id={}, diagnostics={})

    candidates = [
        CrossRerankCandidate(
            rule_id=str(item.get("rule_id", "")),
            score=float(item.get("score", 0.0) or 0.0),
            candidate_text=str(item.get("candidate_text", "")),
        )
        for item in data.get("candidates", [])
        if item.get("rule_id")
    ]
    metadata_by_rule_id = {
        candidate.rule_id: {
            "cross_rerank_score": candidate.score,
        }
        for candidate in candidates
    }
    return CrossRerankResult(
        candidates=candidates,
        metadata_by_rule_id=metadata_by_rule_id,
        diagnostics=dict(data.get("diagnostics", {})),
    )
