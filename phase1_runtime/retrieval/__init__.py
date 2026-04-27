from __future__ import annotations

from .asset_index import build_rule_asset_index
from .case_retrieval import CaseMatch, retrieve_similar_cases, should_shortcut
from .cross_rerank import cross_rerank_available, cross_rerank_candidates
from .dense_retrieval import dense_retrieval_available, rerank_hybrid_matches, retrieve_dense_candidates
from .embedding_backend import available_embedding_backends, default_embedding_backend, semantic_similarity_matrix, semantic_similarity_score
from .embedding_backend_service import get_active_embedding_backend_metadata, get_embedding_backend_status
from .hybrid_retrieval import retrieve_hybrid_matches_from_rules
from .query_rewrite import rewrite_retrieval_query
from .retrieval import MatchResult, retrieve_candidates, score_rule, select_composable_candidates, select_direct_match
from .retrieval_query import build_retrieval_query
from .rule_graph import build_rule_graph_index, route_query_to_rule_graph
from .rule_graph_rag import build_rule_graph_rag_catalog, retrieve_rule_graph_rag
from .rule_graph_store import (
    DEFAULT_RULE_GRAPH_STATE_DIR,
    fingerprint_rules,
    load_or_build_rule_graph_artifacts,
    load_persisted_rule_graph_artifacts,
    materialize_rule_graph_artifacts,
)
from .semantic_similarity import semantic_similarity


__all__ = [
    "CaseMatch",
    "MatchResult",
    "available_embedding_backends",
    "build_retrieval_query",
    "build_rule_asset_index",
    "build_rule_graph_index",
    "build_rule_graph_rag_catalog",
    "cross_rerank_available",
    "cross_rerank_candidates",
    "default_embedding_backend",
    "DEFAULT_RULE_GRAPH_STATE_DIR",
    "dense_retrieval_available",
    "fingerprint_rules",
    "get_active_embedding_backend_metadata",
    "get_embedding_backend_status",
    "load_or_build_rule_graph_artifacts",
    "load_persisted_rule_graph_artifacts",
    "materialize_rule_graph_artifacts",
    "rerank_hybrid_matches",
    "retrieve_candidates",
    "retrieve_dense_candidates",
    "retrieve_hybrid_matches_from_rules",
    "retrieve_similar_cases",
    "rewrite_retrieval_query",
    "score_rule",
    "select_composable_candidates",
    "select_direct_match",
    "semantic_similarity",
    "semantic_similarity_matrix",
    "semantic_similarity_score",
    "retrieve_rule_graph_rag",
    "route_query_to_rule_graph",
    "should_shortcut",
]
