from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from .asset_index import build_rule_asset_index
from .hybrid_retrieval_types import IndexedAssetRecord, RetrievalQuery, tokenize_text

try:
    import igraph as ig
    import leidenalg
except Exception:  # pragma: no cover - optional dependency fallback
    ig = None
    leidenalg = None

try:
    import networkx as nx
    from networkx.algorithms.community import greedy_modularity_communities
except Exception:  # pragma: no cover - optional dependency fallback
    nx = None
    greedy_modularity_communities = None


@dataclass(slots=True)
class MetaRuleSummary:
    meta_rule_id: str
    label: str
    dominant_rule_family: str
    rule_ids: list[str]
    question_types: list[str]
    intents: list[str]
    document_types: list[str]
    required_input_keys: list[str]
    output_keys: list[str]
    summary: str
    support_terms: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetaRuleSummary":
        return cls(
            meta_rule_id=str(data.get("meta_rule_id", "")),
            label=str(data.get("label", "")),
            dominant_rule_family=str(data.get("dominant_rule_family", "")),
            rule_ids=[str(item) for item in data.get("rule_ids", [])],
            question_types=[str(item) for item in data.get("question_types", [])],
            intents=[str(item) for item in data.get("intents", [])],
            document_types=[str(item) for item in data.get("document_types", [])],
            required_input_keys=[str(item) for item in data.get("required_input_keys", [])],
            output_keys=[str(item) for item in data.get("output_keys", [])],
            summary=str(data.get("summary", "")),
            support_terms={str(item) for item in data.get("support_terms", [])},
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta_rule_id": self.meta_rule_id,
            "label": self.label,
            "dominant_rule_family": self.dominant_rule_family,
            "rule_ids": list(self.rule_ids),
            "question_types": list(self.question_types),
            "intents": list(self.intents),
            "document_types": list(self.document_types),
            "required_input_keys": list(self.required_input_keys),
            "output_keys": list(self.output_keys),
            "summary": self.summary,
            "support_terms": sorted(self.support_terms),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class CommunityReport:
    report_id: str
    title: str
    summary: str
    findings: list[str]
    representative_rules: list[str]
    focus_terms: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommunityReport":
        return cls(
            report_id=str(data.get("report_id", "")),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            findings=[str(item) for item in data.get("findings", [])],
            representative_rules=[str(item) for item in data.get("representative_rules", [])],
            focus_terms=[str(item) for item in data.get("focus_terms", [])],
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "summary": self.summary,
            "findings": list(self.findings),
            "representative_rules": list(self.representative_rules),
            "focus_terms": list(self.focus_terms),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class RuleCommunity:
    community_id: str
    level: int
    parent_community_id: str | None
    child_community_ids: list[str]
    rule_ids: list[str]
    meta_rule: MetaRuleSummary
    report: CommunityReport
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleCommunity":
        return cls(
            community_id=str(data.get("community_id", "")),
            level=int(data.get("level", 0) or 0),
            parent_community_id=None if data.get("parent_community_id") is None else str(data.get("parent_community_id")),
            child_community_ids=[str(item) for item in data.get("child_community_ids", [])],
            rule_ids=[str(item) for item in data.get("rule_ids", [])],
            meta_rule=MetaRuleSummary.from_dict(dict(data.get("meta_rule", {}))),
            report=CommunityReport.from_dict(dict(data.get("report", {}))),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "community_id": self.community_id,
            "level": self.level,
            "parent_community_id": self.parent_community_id,
            "child_community_ids": list(self.child_community_ids),
            "rule_ids": list(self.rule_ids),
            "meta_rule": self.meta_rule.to_dict(),
            "report": self.report.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class RuleGraphIndex:
    records: list[IndexedAssetRecord]
    communities: list[RuleCommunity]
    community_by_rule_id: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def records_by_rule_id(self) -> dict[str, IndexedAssetRecord]:
        return {record.rule_id: record for record in self.records}

    @property
    def communities_by_id(self) -> dict[str, RuleCommunity]:
        return {community.community_id: community for community in self.communities}

    @property
    def leaf_communities(self) -> list[RuleCommunity]:
        return [community for community in self.communities if not community.child_community_ids]

    @property
    def root_communities(self) -> list[RuleCommunity]:
        return [community for community in self.communities if community.parent_community_id is None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": len(self.records),
            "community_count": len(self.communities),
            "community_by_rule_id": dict(self.community_by_rule_id),
            "communities": [community.to_dict() for community in self.communities],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class RuleGraphRoute:
    candidate_rule_ids: list[str]
    selected_community_ids: list[str]
    selected_meta_rule_ids: list[str]
    community_scores: list[dict[str, Any]]
    route_metadata_by_rule_id: dict[str, dict[str, Any]]
    used_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_rule_ids": list(self.candidate_rule_ids),
            "selected_community_ids": list(self.selected_community_ids),
            "selected_meta_rule_ids": list(self.selected_meta_rule_ids),
            "community_scores": [dict(item) for item in self.community_scores],
            "route_metadata_by_rule_id": {key: dict(value) for key, value in self.route_metadata_by_rule_id.items()},
            "used_fallback": self.used_fallback,
        }


def _pair_weight(left: IndexedAssetRecord, right: IndexedAssetRecord) -> int:
    weight = 0
    if left.rule_family == right.rule_family:
        weight += 10
    weight += len(left.question_types & right.question_types) * 2
    weight += len(left.intents & right.intents)
    weight += len(left.document_types & right.document_types)
    weight += len(left.required_input_keys & right.required_input_keys) * 5
    weight += len(left.optional_input_keys & right.optional_input_keys) * 2
    weight += len(left.output_keys & right.output_keys) * 3
    weight += min(6, len(left.query_signals & right.query_signals) * 3)
    support_overlap = len(left.support_terms & right.support_terms)
    if support_overlap >= 4:
        weight += min(3, support_overlap // 3)

    left_rule = left.rule
    right_rule = right.rule
    if left_rule and left_rule.composition and right.rule_id in left_rule.composition.source_rule_ids:
        weight += 12
    if right_rule and right_rule.composition and left.rule_id in right_rule.composition.source_rule_ids:
        weight += 12
    return weight


def _top_items(counter: Counter[str], limit: int = 5) -> list[str]:
    return [item for item, _count in counter.most_common(limit)]


def _build_meta_rule(
    community_id: str,
    rule_ids: list[str],
    records_by_rule_id: dict[str, IndexedAssetRecord],
    *,
    edge_count: int,
    total_weight: int,
) -> MetaRuleSummary:
    family_counter: Counter[str] = Counter()
    question_type_counter: Counter[str] = Counter()
    intent_counter: Counter[str] = Counter()
    document_type_counter: Counter[str] = Counter()
    required_input_counter: Counter[str] = Counter()
    output_counter: Counter[str] = Counter()
    support_term_counter: Counter[str] = Counter()

    for rule_id in rule_ids:
        record = records_by_rule_id[rule_id]
        family_counter[record.rule_family] += 1
        question_type_counter.update(record.question_types)
        intent_counter.update(record.intents)
        document_type_counter.update(record.document_types)
        required_input_counter.update(record.required_input_keys)
        output_counter.update(record.output_keys)
        support_term_counter.update(record.query_signals)
        support_term_counter.update(record.support_terms)

    dominant_rule_family = family_counter.most_common(1)[0][0] if family_counter else "misc"
    top_question_types = _top_items(question_type_counter, limit=4)
    top_intents = _top_items(intent_counter, limit=4)
    top_document_types = _top_items(document_type_counter, limit=4)
    top_required_inputs = _top_items(required_input_counter, limit=6)
    top_output_keys = _top_items(output_counter, limit=6)
    top_support_terms = _top_items(support_term_counter, limit=12)

    label_bits = [dominant_rule_family]
    if top_question_types:
        label_bits.append(top_question_types[0])
    if top_intents:
        label_bits.append(top_intents[0])
    label = "::".join(label_bits)
    summary = (
        f"Meta-rule community for `{dominant_rule_family}` tasks covering "
        f"{', '.join(top_question_types or ['general'])} with "
        f"{', '.join(top_required_inputs[:3] or ['context-driven inputs'])} "
        "as dominant inputs."
    )
    return MetaRuleSummary(
        meta_rule_id=f"meta_rule_{community_id}",
        label=label,
        dominant_rule_family=dominant_rule_family,
        rule_ids=list(rule_ids),
        question_types=top_question_types,
        intents=top_intents,
        document_types=top_document_types,
        required_input_keys=top_required_inputs,
        output_keys=top_output_keys,
        summary=summary,
        support_terms=set(top_support_terms)
        | tokenize_text(dominant_rule_family)
        | set(top_required_inputs)
        | set(top_output_keys),
        metadata={
            "rule_count": len(rule_ids),
            "edge_count": edge_count,
            "total_weight": total_weight,
            "top_support_terms": top_support_terms,
        },
    )


def _build_community_report(
    *,
    community_id: str,
    level: int,
    parent_community_id: str | None,
    child_community_ids: list[str],
    meta_rule: MetaRuleSummary,
    rule_ids: list[str],
) -> CommunityReport:
    hierarchy_label = "leaf" if not child_community_ids else ("root" if parent_community_id is None else "intermediate")
    findings = [
        f"Dominant rule family: {meta_rule.dominant_rule_family}",
        (
            "Common required inputs: "
            + ", ".join(meta_rule.required_input_keys[:4])
            if meta_rule.required_input_keys
            else "Common required inputs: context-driven"
        ),
        (
            "Common outputs: " + ", ".join(meta_rule.output_keys[:4])
            if meta_rule.output_keys
            else "Common outputs: answer-oriented"
        ),
    ]
    if meta_rule.question_types:
        findings.append("Question types: " + ", ".join(meta_rule.question_types[:4]))
    if meta_rule.intents:
        findings.append("Intents: " + ", ".join(meta_rule.intents[:4]))
    if child_community_ids:
        findings.append(f"Decomposes into {len(child_community_ids)} child communities")

    title = f"{meta_rule.label} [{hierarchy_label}]"
    summary = (
        f"Hierarchical community report for `{meta_rule.dominant_rule_family}` at level {level}. "
        f"It covers {len(rule_ids)} reviewed rules and acts as a "
        f"{'broad routing layer' if child_community_ids else 'local execution neighborhood'}."
    )
    focus_terms = list(dict.fromkeys(meta_rule.required_input_keys + meta_rule.output_keys + list(meta_rule.support_terms)[:8]))
    return CommunityReport(
        report_id=f"community_report_{community_id}",
        title=title,
        summary=summary,
        findings=findings,
        representative_rules=list(rule_ids[:5]),
        focus_terms=list(focus_terms[:16]),
        metadata={
            "community_id": community_id,
            "level": level,
            "hierarchy_label": hierarchy_label,
            "child_count": len(child_community_ids),
            "rule_count": len(rule_ids),
        },
    )


def _split_rule_ids(
    *,
    graph_nx,
    graph_ig,
    igraph_name_to_index: dict[str, int],
    rule_ids: list[str],
) -> list[list[str]]:
    if len(rule_ids) <= 1:
        return []
    if graph_ig is not None and leidenalg is not None:
        vertex_indices = [igraph_name_to_index[rule_id] for rule_id in rule_ids]
        subgraph = graph_ig.induced_subgraph(vertex_indices)
        if subgraph.ecount() == 0:
            return [[rule_id] for rule_id in sorted(rule_ids)]
        weights = list(subgraph.es["weight"]) if "weight" in subgraph.es.attributes() else None
        partition = leidenalg.find_partition(
            subgraph,
            leidenalg.ModularityVertexPartition,
            weights=weights,
            n_iterations=-1,
        )
        groups: dict[int, list[str]] = {}
        for membership, vertex_name in zip(partition.membership, subgraph.vs["name"]):
            groups.setdefault(int(membership), []).append(str(vertex_name))
        detected = [sorted(group) for group in groups.values() if group]
        if len(detected) <= 1:
            return []
        if len(detected) == len(rule_ids) and all(len(group) == 1 for group in detected):
            return detected
        return sorted(detected, key=lambda item: (item[0], len(item)))
    if graph_nx is None or greedy_modularity_communities is None:
        return [[rule_id] for rule_id in sorted(rule_ids)]

    subgraph = graph_nx.subgraph(rule_ids).copy()
    if subgraph.number_of_edges() == 0:
        return [[rule_id] for rule_id in sorted(rule_ids)]

    detected = [sorted(list(group)) for group in greedy_modularity_communities(subgraph, weight="weight") if group]
    if len(detected) <= 1:
        return []
    if len(detected) == len(rule_ids) and all(len(group) == 1 for group in detected):
        return detected
    return sorted(detected, key=lambda item: (item[0], len(item)))


def build_rule_graph_index(rules: Iterable[Any]) -> RuleGraphIndex:
    records = build_rule_asset_index(rules)
    records_by_rule_id = {record.rule_id: record for record in records}
    ordered_rule_ids = [record.rule_id for record in records]
    if not ordered_rule_ids:
        return RuleGraphIndex(records=[], communities=[], community_by_rule_id={}, metadata={"graph_backend": "none"})

    graph_nx = nx.Graph() if nx is not None else None
    edge_weights: dict[tuple[str, str], int] = {}
    if graph_nx is not None:
        graph_nx.add_nodes_from(ordered_rule_ids)

    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            weight = _pair_weight(left, right)
            if weight < 8:
                continue
            key = tuple(sorted((left.rule_id, right.rule_id)))
            edge_weights[key] = weight
            if graph_nx is not None:
                graph_nx.add_edge(left.rule_id, right.rule_id, weight=weight)

    graph_ig = None
    igraph_name_to_index: dict[str, int] = {}
    if ig is not None and leidenalg is not None:
        igraph_name_to_index = {rule_id: index for index, rule_id in enumerate(ordered_rule_ids)}
        igraph_edges = [(igraph_name_to_index[left], igraph_name_to_index[right]) for left, right in edge_weights]
        graph_ig = ig.Graph(n=len(ordered_rule_ids), edges=igraph_edges, directed=False)
        graph_ig.vs["name"] = ordered_rule_ids
        if igraph_edges:
            graph_ig.es["weight"] = [edge_weights[key] for key in edge_weights]

    community_by_rule_id: dict[str, str] = {}
    communities: list[RuleCommunity] = []
    community_counter = 0

    def next_community_id() -> str:
        nonlocal community_counter
        community_id = f"community_{community_counter:03d}"
        community_counter += 1
        return community_id

    def build_hierarchy(rule_ids: list[str], *, level: int, parent_community_id: str | None) -> str:
        community_id = next_community_id()
        edge_count = 0
        total_weight = 0
        for index, left_rule_id in enumerate(rule_ids):
            for right_rule_id in rule_ids[index + 1 :]:
                key = tuple(sorted((left_rule_id, right_rule_id)))
                if key in edge_weights:
                    edge_count += 1
                    total_weight += edge_weights[key]
        child_groups = _split_rule_ids(
            graph_nx=graph_nx,
            graph_ig=graph_ig,
            igraph_name_to_index=igraph_name_to_index,
            rule_ids=rule_ids,
        )
        should_split = (
            len(rule_ids) > 1
            and len(child_groups) > 1
            and any(len(group) < len(rule_ids) for group in child_groups)
        )
        child_community_ids: list[str] = []
        if should_split:
            for group in child_groups:
                child_community_ids.append(
                    build_hierarchy(group, level=level + 1, parent_community_id=community_id)
                )
        meta_rule = _build_meta_rule(
            community_id,
            rule_ids,
            records_by_rule_id,
            edge_count=edge_count,
            total_weight=total_weight,
        )
        report = _build_community_report(
            community_id=community_id,
            level=level,
            parent_community_id=parent_community_id,
            child_community_ids=child_community_ids,
            meta_rule=meta_rule,
            rule_ids=rule_ids,
        )
        communities.append(
            RuleCommunity(
                community_id=community_id,
                level=level,
                parent_community_id=parent_community_id,
                child_community_ids=child_community_ids,
                rule_ids=list(rule_ids),
                meta_rule=meta_rule,
                report=report,
                metadata={
                    "edge_count": edge_count,
                    "total_weight": total_weight,
                    "is_leaf": not child_community_ids,
                },
            )
        )
        if not child_community_ids:
            for rule_id in rule_ids:
                community_by_rule_id[rule_id] = community_id
        return community_id

    build_hierarchy(sorted(ordered_rule_ids), level=0, parent_community_id=None)

    return RuleGraphIndex(
        records=records,
        communities=sorted(communities, key=lambda item: (item.level, item.community_id)),
        community_by_rule_id=community_by_rule_id,
        metadata={
            "graph_backend": (
                "leidenalg_modularity_hierarchical"
                if graph_ig is not None and leidenalg is not None
                else ("networkx.greedy_modularity_hierarchical" if graph_nx is not None else "fallback_hierarchical")
            ),
            "edge_count": len(edge_weights),
            "hierarchy_depth": max((community.level for community in communities), default=0),
        },
    )


def _score_meta_rule(meta_rule: MetaRuleSummary, query: RetrievalQuery) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    question_type_hits = set(meta_rule.question_types) & set(query.question_types)
    if question_type_hits:
        score += len(question_type_hits) * 10
        reasons.append(f"question_types={sorted(question_type_hits)}")

    intent_hits = set(meta_rule.intents) & set(query.intents)
    if intent_hits:
        score += len(intent_hits) * 8
        reasons.append(f"intents={sorted(intent_hits)}")

    document_type_hits = set(meta_rule.document_types) & set(query.document_types)
    if document_type_hits:
        score += len(document_type_hits) * 6
        reasons.append(f"document_types={sorted(document_type_hits)}")

    fact_hits = set(meta_rule.required_input_keys) & set(query.fact_keys)
    if fact_hits:
        score += len(fact_hits) * 8
        reasons.append(f"fact_keys={sorted(fact_hits)}")

    support_hits = meta_rule.support_terms & query.lexical_terms
    if support_hits:
        score += min(12, len(support_hits))
        reasons.append(f"support_terms={sorted(list(support_hits))[:6]}")

    family_hits = tokenize_text(meta_rule.dominant_rule_family) & query.question_terms
    if family_hits:
        score += len(family_hits) * 4
        reasons.append(f"family_terms={sorted(family_hits)}")

    return score, reasons


def _candidate_limit(total_rules: int, top_k: int | None) -> int:
    if total_rules <= 3:
        return total_rules
    if top_k is not None:
        return min(total_rules, max(3, top_k + 2))
    return min(total_rules, max(3, (total_rules + 1) // 2))


def _community_path(index: RuleGraphIndex, community_id: str) -> list[str]:
    path: list[str] = []
    current = index.communities_by_id.get(community_id)
    while current is not None:
        path.append(current.community_id)
        if current.parent_community_id is None:
            break
        current = index.communities_by_id.get(current.parent_community_id)
    return list(reversed(path))


def route_query_to_rule_graph(
    index: RuleGraphIndex,
    query: RetrievalQuery,
    *,
    top_k: int | None = None,
) -> RuleGraphRoute:
    ordered_rule_ids = [record.rule_id for record in index.records]
    if not ordered_rule_ids or not index.leaf_communities:
        return RuleGraphRoute(
            candidate_rule_ids=ordered_rule_ids,
            selected_community_ids=[],
            selected_meta_rule_ids=[],
            community_scores=[],
            route_metadata_by_rule_id={},
            used_fallback=True,
        )

    scored: list[tuple[RuleCommunity, int, list[str]]] = []
    for community in index.leaf_communities:
        score, reasons = _score_meta_rule(community.meta_rule, query)
        scored.append((community, score, reasons))
    scored.sort(key=lambda item: (item[1], len(item[0].rule_ids), item[0].community_id), reverse=True)

    positive_scores = [item for item in scored if item[1] > 0]
    if not positive_scores:
        return RuleGraphRoute(
            candidate_rule_ids=ordered_rule_ids,
            selected_community_ids=[],
            selected_meta_rule_ids=[],
            community_scores=[
                {
                    "community_id": community.community_id,
                    "meta_rule_id": community.meta_rule.meta_rule_id,
                    "meta_rule_label": community.meta_rule.label,
                    "score": score,
                    "reasons": list(reasons),
                }
                for community, score, reasons in scored
            ],
            route_metadata_by_rule_id={},
            used_fallback=True,
        )

    top_score = positive_scores[0][1]
    min_keep_score = max(4, int(top_score * 0.6))
    limit = _candidate_limit(len(ordered_rule_ids), top_k=top_k)

    selected: list[tuple[RuleCommunity, int, list[str]]] = []
    candidate_rule_set: set[str] = set()
    for item in positive_scores:
        community, score, _reasons = item
        if score < min_keep_score:
            continue
        selected.append(item)
        candidate_rule_set.update(community.rule_ids)
        if len(candidate_rule_set) >= limit:
            break

    if not selected:
        return RuleGraphRoute(
            candidate_rule_ids=ordered_rule_ids,
            selected_community_ids=[],
            selected_meta_rule_ids=[],
            community_scores=[
                {
                    "community_id": community.community_id,
                    "meta_rule_id": community.meta_rule.meta_rule_id,
                    "meta_rule_label": community.meta_rule.label,
                    "score": score,
                    "reasons": list(reasons),
                }
                for community, score, reasons in scored
            ],
            route_metadata_by_rule_id={},
            used_fallback=True,
        )

    route_metadata_by_rule_id: dict[str, dict[str, Any]] = {}
    selected_community_ids: list[str] = []
    selected_meta_rule_ids: list[str] = []
    for community, score, reasons in selected:
        selected_community_ids.append(community.community_id)
        selected_meta_rule_ids.append(community.meta_rule.meta_rule_id)
        for rule_id in community.rule_ids:
            route_metadata_by_rule_id[rule_id] = {
                "community_id": community.community_id,
                "meta_rule_id": community.meta_rule.meta_rule_id,
                "meta_rule_label": community.meta_rule.label,
                "community_level": community.level,
                "community_path": _community_path(index, community.community_id),
                "community_score": score,
                "community_reasons": list(reasons),
            }

    candidate_rule_ids = [rule_id for rule_id in ordered_rule_ids if rule_id in candidate_rule_set]
    return RuleGraphRoute(
        candidate_rule_ids=candidate_rule_ids,
        selected_community_ids=selected_community_ids,
        selected_meta_rule_ids=selected_meta_rule_ids,
        community_scores=[
            {
                "community_id": community.community_id,
                "meta_rule_id": community.meta_rule.meta_rule_id,
                "meta_rule_label": community.meta_rule.label,
                "score": score,
                "reasons": list(reasons),
            }
            for community, score, reasons in scored
        ],
        route_metadata_by_rule_id=route_metadata_by_rule_id,
        used_fallback=False,
    )
