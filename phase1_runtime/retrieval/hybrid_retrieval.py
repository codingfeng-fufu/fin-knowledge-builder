from __future__ import annotations

from typing import Iterable

from .asset_index import build_rule_asset_index
from .embedding_backend import default_embedding_backend, semantic_similarity_matrix
from .hybrid_retrieval_types import HybridMatchResult, IndexedAssetRecord, RetrievalQuery


def score_indexed_asset(
    record: IndexedAssetRecord,
    query: RetrievalQuery,
    *,
    min_signal_hits: int = 1,
    semantic_value: float = 0.0,
    semantic_gate_value: float = 0.0,
) -> HybridMatchResult | None:
    if record.status != "published":
        return None

    reasons: list[str] = []
    structured_score = 0

    question_type_overlap = record.question_types & set(query.question_types)
    if not question_type_overlap:
        return None
    structured_score += 12
    reasons.append(f"question_type_match={sorted(question_type_overlap)}")

    intent_overlap = record.intents & set(query.intents)
    if not intent_overlap:
        return None
    structured_score += 10
    reasons.append(f"intent_match={sorted(intent_overlap)}")

    document_type_overlap = record.document_types & set(query.document_types)
    if not document_type_overlap:
        return None
    structured_score += 8
    reasons.append(f"document_type_match={sorted(document_type_overlap)}")

    signal_hits = sum(
        1
        for signal in record.query_signals
        if signal in query.question_terms or signal in query.question_text.lower()
    )
    lexical_overlap = len(query.lexical_terms & record.support_terms)
    fact_hits = len(record.required_input_keys & query.fact_keys)
    optional_fact_hits = len(record.optional_input_keys & query.fact_keys)
    semantic_score = round(semantic_value * 12)
    semantic_gate_score = round(semantic_gate_value * 100)
    negative_hits = len(query.lexical_terms & record.negative_terms)
    semantic_score = max(0, semantic_score - negative_hits * 2)

    passes_signal_threshold = signal_hits >= min_signal_hits
    passes_semantic_threshold = semantic_gate_score >= 4 and fact_hits >= 2
    if passes_signal_threshold:
        reasons.append(f"signal_hits={signal_hits}")
    else:
        reasons.append(f"signal_hits={signal_hits}")
        reasons.append("below_signal_threshold")
    if semantic_score:
        reasons.append(f"semantic_score={semantic_score}")
    if semantic_gate_score:
        reasons.append(f"semantic_gate_score={semantic_gate_score}")
    if negative_hits:
        reasons.append(f"negative_hits={negative_hits}")

    if lexical_overlap:
        reasons.append(f"lexical_overlap={lexical_overlap}")
    if fact_hits:
        reasons.append(f"required_fact_hits={fact_hits}")
    if optional_fact_hits:
        reasons.append(f"optional_fact_hits={optional_fact_hits}")

    score_breakdown = {
        "structured": structured_score,
        "lexical": signal_hits * 8 + lexical_overlap * 2,
        "fact": fact_hits * 5 + optional_fact_hits * 2,
        "semantic": semantic_score,
        "rule_shape": int(record.metadata.get("step_count", 0)),
    }
    score_total = sum(score_breakdown.values())
    retrieval_gate = passes_signal_threshold or passes_semantic_threshold
    eligible_for_direct_match = record.rule_kind != "atomic" and retrieval_gate
    eligible_for_composition = record.rule_kind == "atomic" and retrieval_gate
    return HybridMatchResult(
        record=record,
        score_total=score_total,
        score_breakdown=score_breakdown,
        reasons=reasons,
        signal_hits=signal_hits,
        lexical_hits=lexical_overlap,
        fact_hits=fact_hits + optional_fact_hits,
        eligible_for_direct_match=eligible_for_direct_match,
        eligible_for_composition=eligible_for_composition,
    )


def rank_hybrid_matches(
    records: Iterable[IndexedAssetRecord],
    query: RetrievalQuery,
    *,
    min_signal_hits: int = 1,
    top_k: int | None = None,
) -> list[HybridMatchResult]:
    record_list = list(records)
    if not record_list:
        return []
    backend = default_embedding_backend()
    semantic_values = semantic_similarity_matrix(
        [query.semantic_text],
        [record.semantic_text for record in record_list],
        backend=backend,
    )[0]
    semantic_gate_values = semantic_similarity_matrix(
        [query.question_semantic_text],
        [record.semantic_focus_text for record in record_list],
        backend=backend,
    )[0]
    ranked = sorted(
        (
            match
            for index, record in enumerate(record_list)
            if (
                match := score_indexed_asset(
                    record,
                    query,
                    min_signal_hits=min_signal_hits,
                    semantic_value=float(semantic_values[index]),
                    semantic_gate_value=float(semantic_gate_values[index]),
                )
            ) is not None
        ),
        key=lambda item: (
            item.eligible_for_direct_match,
            item.eligible_for_composition,
            item.score_total,
            item.fact_hits,
            item.signal_hits,
            item.lexical_hits,
        ),
        reverse=True,
    )
    if top_k is None:
        return ranked
    return ranked[:top_k]


def retrieve_hybrid_matches_from_rules(
    rules,
    query: RetrievalQuery,
    *,
    min_signal_hits: int = 1,
    top_k: int | None = None,
) -> list[HybridMatchResult]:
    return rank_hybrid_matches(
        build_rule_asset_index(rules),
        query,
        min_signal_hits=min_signal_hits,
        top_k=top_k,
    )
