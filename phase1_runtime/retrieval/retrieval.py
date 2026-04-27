from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .cross_rerank import cross_rerank_candidates
from .dense_retrieval import rerank_hybrid_matches, retrieve_dense_candidates
from ..schema import QuestionStruct, Rule
from .hybrid_retrieval import retrieve_hybrid_matches_from_rules
from .rule_graph import route_query_to_rule_graph
from .rule_graph_rag import retrieve_rule_graph_rag
from .rule_graph_store import load_or_build_rule_graph_artifacts
from .retrieval_query import build_retrieval_query


@dataclass(slots=True)
class MatchResult:
    rule: Rule
    score: int
    reasons: list[str]
    signal_hits: int
    eligible_for_direct_match: bool
    eligible_for_composition: bool
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule.rule_id,
            "name": self.rule.name,
            "rule_kind": self.rule.rule_kind,
            "rule_family": self.rule.rule_family,
            "score": self.score,
            "signal_hits": self.signal_hits,
            "eligible_for_direct_match": self.eligible_for_direct_match,
            "eligible_for_composition": self.eligible_for_composition,
            "reasons": self.reasons,
            "metadata": dict(self.metadata),
        }


def _adapt_match(
    match,
    *,
    route_metadata: dict[str, object] | None = None,
    rag_metadata: dict[str, object] | None = None,
    dense_metadata: dict[str, object] | None = None,
    cross_metadata: dict[str, object] | None = None,
    retrieval_diagnostics: dict[str, object] | None = None,
    final_score: int | None = None,
) -> MatchResult:
    if match.record.rule is None:
        raise ValueError(f"hybrid match missing bound rule: {match.record.rule_id}")
    reasons = list(match.reasons)
    metadata: dict[str, object] = {}
    if route_metadata:
        metadata.update(route_metadata)
        community_id = route_metadata.get("community_id")
        if isinstance(community_id, str) and community_id:
            reasons.append(f"graph_community={community_id}")
        meta_rule_label = route_metadata.get("meta_rule_label")
        if isinstance(meta_rule_label, str) and meta_rule_label:
            reasons.append(f"graph_meta_rule={meta_rule_label}")
        community_level = route_metadata.get("community_level")
        if isinstance(community_level, int):
            reasons.append(f"graph_community_level={community_level}")
        community_path = route_metadata.get("community_path")
        if isinstance(community_path, list) and community_path:
            reasons.append(f"graph_community_path={'/'.join(str(item) for item in community_path)}")
        community_score = route_metadata.get("community_score")
        if isinstance(community_score, int):
            reasons.append(f"graph_route_score={community_score}")
    if rag_metadata:
        metadata.update(rag_metadata)
        graph_rag_hits = rag_metadata.get("graph_rag_hits")
        if isinstance(graph_rag_hits, int):
            reasons.append(f"graph_rag_hits={graph_rag_hits}")
        top_passage_type = rag_metadata.get("top_passage_type")
        if isinstance(top_passage_type, str) and top_passage_type:
            reasons.append(f"graph_rag_top_passage={top_passage_type}")
    if dense_metadata:
        metadata.update(dense_metadata)
        dense_score = dense_metadata.get("dense_score")
        if isinstance(dense_score, (int, float)):
            reasons.append(f"dense_score={round(float(dense_score), 4)}")
        dense_hits = dense_metadata.get("dense_hits")
        if isinstance(dense_hits, int):
            reasons.append(f"dense_hits={dense_hits}")
        dense_top_passage_type = dense_metadata.get("dense_top_passage_type")
        if isinstance(dense_top_passage_type, str) and dense_top_passage_type:
            reasons.append(f"dense_top_passage={dense_top_passage_type}")
    if cross_metadata:
        metadata.update(cross_metadata)
        cross_score = cross_metadata.get("cross_rerank_score")
        if isinstance(cross_score, (int, float)):
            reasons.append(f"cross_rerank_score={round(float(cross_score), 4)}")
    if retrieval_diagnostics:
        metadata["retrieval_diagnostics"] = dict(retrieval_diagnostics)
    reasons.append(f"score_total={match.score_total}")
    return MatchResult(
        rule=match.record.rule,
        score=match.score_total if final_score is None else final_score,
        reasons=reasons,
        signal_hits=match.signal_hits,
        eligible_for_direct_match=match.eligible_for_direct_match,
        eligible_for_composition=match.eligible_for_composition,
        metadata=metadata,
    )


def score_rule(
    rule: Rule,
    question: QuestionStruct,
    min_signal_hits: int = 1,
    *,
    facts: dict[str, object] | None = None,
    evidence_refs: list[object] | None = None,
    retrieval_fact_keys: set[str] | list[str] | None = None,
) -> MatchResult | None:
    query = build_retrieval_query(
        question,
        facts=facts,
        evidence_refs=evidence_refs,
        retrieval_fact_keys=retrieval_fact_keys,
    )
    matches = retrieve_hybrid_matches_from_rules([rule], query, min_signal_hits=min_signal_hits, top_k=1)
    if not matches:
        return None
    return _adapt_match(matches[0])


def retrieve_candidates(
    rules: Iterable[Rule],
    question: QuestionStruct,
    min_signal_hits: int = 1,
    top_k: int | None = None,
    *,
    facts: dict[str, object] | None = None,
    evidence_refs: list[object] | None = None,
    retrieval_fact_keys: set[str] | list[str] | None = None,
) -> list[MatchResult]:
    rule_list = list(rules)
    query = build_retrieval_query(
        question,
        facts=facts,
        evidence_refs=evidence_refs,
        retrieval_fact_keys=retrieval_fact_keys,
    )
    route = None
    graph_index = None
    rag_catalog = None
    graph_store_metadata = None
    routed_rule_ids: list[str] = []
    dense = None
    cross = None
    if len(rule_list) > 1:
        graph_index, rag_catalog, graph_store_metadata = load_or_build_rule_graph_artifacts(rule_list)
        route = route_query_to_rule_graph(graph_index, query, top_k=top_k)
        routed_rule_ids = list(route.candidate_rule_ids)
        if graph_store_metadata is not None:
            dense = retrieve_dense_candidates(
                artifact_root=graph_store_metadata["artifact_root"],
                passages=rag_catalog,
                query=query,
                top_k=12 if top_k is None else max(8, top_k * 3),
            )
    candidate_rule_ids = set(routed_rule_ids)
    if dense is not None:
        candidate_rule_ids.update(candidate.rule_id for candidate in dense.candidates)
    routed_rules = [rule for rule in rule_list if rule.rule_id in candidate_rule_ids] if candidate_rule_ids else rule_list
    matches = retrieve_hybrid_matches_from_rules(
        routed_rules,
        query,
        min_signal_hits=min_signal_hits,
        top_k=top_k,
    )
    if routed_rules != rule_list and not any(match.eligible_for_direct_match or match.eligible_for_composition for match in matches):
        matches = retrieve_hybrid_matches_from_rules(
            rule_list,
            query,
            min_signal_hits=min_signal_hits,
            top_k=top_k,
        )
        route = None
    rag = None
    if graph_index is not None:
        rag_top_k = 6 if top_k is None else max(4, top_k * 2)
        rag = retrieve_rule_graph_rag(graph_index, query, route=route, top_k=rag_top_k, catalog=rag_catalog)
    matches = rerank_hybrid_matches(matches, dense_result=dense, graph_rag_result=rag, route=route)
    if rag_catalog is not None and matches:
        cross = cross_rerank_candidates(
            query_text=query.semantic_text,
            candidate_rule_ids=[match.record.rule_id for match in matches],
            rag_catalog=rag_catalog,
            top_n=8 if top_k is None else max(4, top_k * 2),
        )
        cross_metadata_by_rule_id = cross.metadata_by_rule_id
        matches = sorted(
            matches,
            key=lambda match: (
                float(cross_metadata_by_rule_id.get(match.record.rule_id, {}).get("cross_rerank_score", 0.0)) * 10.0
                + float(match.score_total),
                match.eligible_for_direct_match,
                match.eligible_for_composition,
                match.signal_hits,
            ),
            reverse=True,
        )
    else:
        cross_metadata_by_rule_id = {}

    retrieval_diagnostics = {
        "query_rewrites": [] if dense is None else [rewrite.to_dict() for rewrite in dense.rewrites],
        "dense": {} if dense is None else dict(dense.diagnostics),
        "cross_rerank": {} if cross is None else dict(cross.diagnostics),
    }

    dense_metadata_by_rule_id = {} if dense is None else dense.metadata_by_rule_id
    rag_metadata_by_rule_id = {} if rag is None else rag.metadata_by_rule_id
    route_metadata_by_rule_id = {} if route is None else route.route_metadata_by_rule_id

    def _final_score_for_rule(rule_id: str, hybrid_score: int) -> int:
        dense_score = float(dense_metadata_by_rule_id.get(rule_id, {}).get("dense_score", 0.0))
        dense_hits = int(dense_metadata_by_rule_id.get(rule_id, {}).get("dense_hits", 0))
        graph_rag_hits = int(rag_metadata_by_rule_id.get(rule_id, {}).get("graph_rag_hits", 0))
        graph_route_score = int(route_metadata_by_rule_id.get(rule_id, {}).get("community_score", 0))
        cross_score = float(cross_metadata_by_rule_id.get(rule_id, {}).get("cross_rerank_score", 0.0))
        return int(round(hybrid_score + dense_score * 20.0 + dense_hits * 4.0 + graph_rag_hits * 2.0 + graph_route_score * 0.15 + cross_score * 10.0))

    return [
        _adapt_match(
            match,
            route_metadata=route_metadata_by_rule_id.get(match.record.rule_id),
            rag_metadata=rag_metadata_by_rule_id.get(match.record.rule_id),
            dense_metadata=dense_metadata_by_rule_id.get(match.record.rule_id),
            cross_metadata=cross_metadata_by_rule_id.get(match.record.rule_id),
            retrieval_diagnostics=retrieval_diagnostics,
            final_score=_final_score_for_rule(match.record.rule_id, match.score_total),
        )
        for match in matches
    ]


def select_direct_match(
    rules: Iterable[Rule],
    question: QuestionStruct,
    min_signal_hits: int = 1,
    *,
    facts: dict[str, object] | None = None,
    evidence_refs: list[object] | None = None,
    retrieval_fact_keys: set[str] | list[str] | None = None,
) -> MatchResult | None:
    for candidate in retrieve_candidates(
        rules,
        question,
        min_signal_hits=min_signal_hits,
        facts=facts,
        evidence_refs=evidence_refs,
        retrieval_fact_keys=retrieval_fact_keys,
    ):
        if candidate.eligible_for_direct_match:
            return candidate
    return None


def select_composable_candidates(candidates: Iterable[MatchResult]) -> list[MatchResult]:
    return [candidate for candidate in candidates if candidate.eligible_for_composition]
