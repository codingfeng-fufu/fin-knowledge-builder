from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from ..schema import Rule


TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_.]+")


def tokenize_text(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def normalize_value_terms(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, bool):
        return {"true" if value else "false"}
    if isinstance(value, (int, float)):
        return {str(value)}
    if isinstance(value, str):
        return tokenize_text(value)
    if isinstance(value, (list, tuple, set)):
        terms: set[str] = set()
        for item in value:
            terms.update(normalize_value_terms(item))
        return terms
    if isinstance(value, dict):
        terms: set[str] = set()
        for key, item in value.items():
            terms.update(tokenize_text(str(key)))
            terms.update(normalize_value_terms(item))
        return terms
    return tokenize_text(str(value))


@dataclass(slots=True)
class RetrievalQuery:
    question_text: str
    question_types: list[str]
    intents: list[str]
    document_types: list[str]
    extracted_inputs: dict[str, Any]
    fact_values: dict[str, Any]
    fact_keys: set[str]
    question_terms: set[str]
    evidence_terms: set[str]
    lexical_terms: set[str]
    semantic_text: str
    semantic_terms: set[str]
    question_semantic_text: str
    question_semantic_terms: set[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_text": self.question_text,
            "question_types": list(self.question_types),
            "intents": list(self.intents),
            "document_types": list(self.document_types),
            "extracted_inputs": dict(self.extracted_inputs),
            "fact_values": dict(self.fact_values),
            "fact_keys": sorted(self.fact_keys),
            "question_terms": sorted(self.question_terms),
            "evidence_terms": sorted(self.evidence_terms),
            "lexical_terms": sorted(self.lexical_terms),
            "semantic_text": self.semantic_text,
            "semantic_terms": sorted(self.semantic_terms),
            "question_semantic_text": self.question_semantic_text,
            "question_semantic_terms": sorted(self.question_semantic_terms),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class IndexedAssetRecord:
    asset_type: str
    asset_id: str
    rule_id: str
    rule_kind: str
    rule_family: str
    status: str
    question_types: set[str]
    intents: set[str]
    document_types: set[str]
    query_signals: set[str]
    support_terms: set[str]
    semantic_text: str
    semantic_terms: set[str]
    semantic_focus_text: str
    semantic_focus_terms: set[str]
    negative_terms: set[str]
    required_input_keys: set[str]
    optional_input_keys: set[str]
    output_keys: set[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    rule: Rule | None = None

    @property
    def lexical_terms(self) -> set[str]:
        return set(self.query_signals) | set(self.support_terms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "asset_id": self.asset_id,
            "rule_id": self.rule_id,
            "rule_kind": self.rule_kind,
            "rule_family": self.rule_family,
            "status": self.status,
            "question_types": sorted(self.question_types),
            "intents": sorted(self.intents),
            "document_types": sorted(self.document_types),
            "query_signals": sorted(self.query_signals),
            "support_terms": sorted(self.support_terms),
            "semantic_text": self.semantic_text,
            "semantic_terms": sorted(self.semantic_terms),
            "semantic_focus_text": self.semantic_focus_text,
            "semantic_focus_terms": sorted(self.semantic_focus_terms),
            "negative_terms": sorted(self.negative_terms),
            "required_input_keys": sorted(self.required_input_keys),
            "optional_input_keys": sorted(self.optional_input_keys),
            "output_keys": sorted(self.output_keys),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class HybridMatchResult:
    record: IndexedAssetRecord
    score_total: int
    score_breakdown: dict[str, int]
    reasons: list[str]
    signal_hits: int
    lexical_hits: int
    fact_hits: int
    eligible_for_direct_match: bool
    eligible_for_composition: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.record.rule_id,
            "asset_id": self.record.asset_id,
            "asset_type": self.record.asset_type,
            "rule_kind": self.record.rule_kind,
            "rule_family": self.record.rule_family,
            "score": self.score_total,
            "signal_hits": self.signal_hits,
            "lexical_hits": self.lexical_hits,
            "fact_hits": self.fact_hits,
            "eligible_for_direct_match": self.eligible_for_direct_match,
            "eligible_for_composition": self.eligible_for_composition,
            "score_breakdown": dict(self.score_breakdown),
            "reasons": list(self.reasons),
        }
