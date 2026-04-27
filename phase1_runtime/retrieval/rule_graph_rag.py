from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .embedding_backend import semantic_similarity_score
from .hybrid_retrieval_types import RetrievalQuery, tokenize_text
from .rule_graph import RuleGraphIndex, RuleGraphRoute


@dataclass(slots=True)
class RuleRagPassage:
    passage_id: str
    rule_id: str | None
    community_id: str | None
    meta_rule_id: str | None
    passage_type: str
    text: str
    score: int
    reasons: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleRagPassage":
        return cls(
            passage_id=str(data.get("passage_id", "")),
            rule_id=None if data.get("rule_id") is None else str(data.get("rule_id")),
            community_id=None if data.get("community_id") is None else str(data.get("community_id")),
            meta_rule_id=None if data.get("meta_rule_id") is None else str(data.get("meta_rule_id")),
            passage_type=str(data.get("passage_type", "")),
            text=str(data.get("text", "")),
            score=int(data.get("score", 0) or 0),
            reasons=[str(item) for item in data.get("reasons", [])],
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passage_id": self.passage_id,
            "rule_id": self.rule_id,
            "community_id": self.community_id,
            "meta_rule_id": self.meta_rule_id,
            "passage_type": self.passage_type,
            "text": self.text,
            "score": self.score,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class RuleGraphRagResult:
    passages: list[RuleRagPassage]
    metadata_by_rule_id: dict[str, dict[str, Any]]
    community_reports: list[RuleRagPassage]
    used_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passages": [passage.to_dict() for passage in self.passages],
            "metadata_by_rule_id": {key: dict(value) for key, value in self.metadata_by_rule_id.items()},
            "community_reports": [passage.to_dict() for passage in self.community_reports],
            "used_fallback": self.used_fallback,
        }


def _rule_overview_text(record) -> str:
    rule = record.rule
    parts = [
        record.rule_id,
        rule.name if rule else "",
        record.rule_family,
        " ".join(sorted(record.query_signals)),
        rule.applicability.scope if rule else "",
        rule.applicability.non_scope if rule else "",
    ]
    return "\n".join(part for part in parts if part)


def _rule_inputs_text(record) -> str:
    rule = record.rule
    if rule is None:
        return ""
    parts = []
    for field in rule.inputs.required:
        parts.append(f"required:{field.key}:{field.description}")
    for field in rule.inputs.optional:
        parts.append(f"optional:{field.key}:{field.description}")
    return "\n".join(parts)


def _rule_steps_text(record) -> str:
    rule = record.rule
    if rule is None:
        return ""
    parts = []
    for step in rule.steps:
        outputs = ",".join(output.key for output in step.io.outputs)
        parts.append(
            f"{step.step_id}:{step.type}:{step.goal}:inputs={','.join(step.io.inputs)}:outputs={outputs}"
        )
    return "\n".join(parts)


def _rule_outputs_text(record) -> str:
    rule = record.rule
    if rule is None:
        return ""
    must_include = ",".join(rule.outputs.must_include)
    answer_keys = ",".join(sorted(record.output_keys))
    validators = ",".join(validator.validator_id for validator in rule.validators)
    return "\n".join(
        part
        for part in [
            f"outputs:{answer_keys}",
            f"must_include:{must_include}",
            f"validators:{validators}",
        ]
        if part and not part.endswith(":")
    )


def _rule_composition_text(record) -> str:
    rule = record.rule
    if rule is None or rule.composition is None:
        return ""
    return (
        f"composition pattern:{rule.composition.pattern}\n"
        f"source_rule_ids:{','.join(rule.composition.source_rule_ids)}"
    )


def _community_report_text(community) -> str:
    report = community.report
    findings = "\n".join(f"- {item}" for item in report.findings)
    representative_rules = "\n".join(f"- {item}" for item in report.representative_rules)
    return "\n".join(
        part
        for part in [
            f"# {report.title}",
            f"Level: {community.level}",
            f"Summary: {report.summary}",
            "Findings:",
            findings,
            "Representative Rules:",
            representative_rules,
            f"Focus Terms: {', '.join(report.focus_terms)}" if report.focus_terms else "",
        ]
        if part
    )


def build_rule_graph_rag_catalog(index: RuleGraphIndex) -> list[RuleRagPassage]:
    passages: list[RuleRagPassage] = []
    for community in index.communities:
        report_text = _community_report_text(community)
        passages.append(
            RuleRagPassage(
                passage_id=f"{community.community_id}:community_report",
                rule_id=None,
                community_id=community.community_id,
                meta_rule_id=community.meta_rule.meta_rule_id,
                passage_type="community_report",
                text=report_text,
                score=0,
                reasons=[],
                metadata={
                    "meta_rule_label": community.meta_rule.label,
                    "community_level": community.level,
                    "parent_community_id": community.parent_community_id,
                    "child_community_ids": list(community.child_community_ids),
                },
            )
        )
    for record in index.records:
        community_id = index.community_by_rule_id.get(record.rule_id)
        meta_rule_id = None
        for community in index.communities:
            if community.community_id == community_id:
                meta_rule_id = community.meta_rule.meta_rule_id
                break
        for passage_type, text in (
            ("rule_overview", _rule_overview_text(record)),
            ("rule_inputs", _rule_inputs_text(record)),
            ("rule_steps", _rule_steps_text(record)),
            ("rule_outputs", _rule_outputs_text(record)),
            ("rule_composition", _rule_composition_text(record)),
        ):
            if not text:
                continue
            passages.append(
                RuleRagPassage(
                    passage_id=f"{record.rule_id}:{passage_type}",
                    rule_id=record.rule_id,
                    community_id=community_id,
                    meta_rule_id=meta_rule_id,
                    passage_type=passage_type,
                    text=text,
                    score=0,
                    reasons=[],
                    metadata={"rule_family": record.rule_family},
                )
            )
    return passages


def _passage_score(text: str, query: RetrievalQuery, *, extra_terms: set[str] | None = None) -> tuple[int, list[str]]:
    reasons: list[str] = []
    terms = tokenize_text(text)
    if extra_terms:
        terms = terms | set(extra_terms)
    lexical_hits = len(terms & query.lexical_terms)
    fact_hits = len(terms & query.fact_keys)
    question_hits = len(terms & query.question_terms)
    semantic_score = round(semantic_similarity_score(query.semantic_text, text) * 10)
    score = lexical_hits * 3 + fact_hits * 5 + question_hits * 2 + semantic_score
    if lexical_hits:
        reasons.append(f"lexical_hits={lexical_hits}")
    if fact_hits:
        reasons.append(f"fact_hits={fact_hits}")
    if question_hits:
        reasons.append(f"question_hits={question_hits}")
    if semantic_score:
        reasons.append(f"semantic={semantic_score}")
    return score, reasons


def retrieve_rule_graph_rag(
    index: RuleGraphIndex,
    query: RetrievalQuery,
    *,
    route: RuleGraphRoute | None = None,
    top_k: int = 6,
    catalog: list[RuleRagPassage] | None = None,
) -> RuleGraphRagResult:
    candidate_rule_ids = set(route.candidate_rule_ids) if route is not None and route.candidate_rule_ids else {
        record.rule_id for record in index.records
    }
    selected_community_ids = set(route.selected_community_ids) if route is not None else set()
    if selected_community_ids:
        expanded_community_ids = set(selected_community_ids)
        communities_by_id = index.communities_by_id
        for community_id in list(selected_community_ids):
            current = communities_by_id.get(community_id)
            while current is not None and current.parent_community_id is not None:
                expanded_community_ids.add(current.parent_community_id)
                current = communities_by_id.get(current.parent_community_id)
        selected_community_ids = expanded_community_ids

    source_passages = build_rule_graph_rag_catalog(index) if catalog is None else list(catalog)
    passages: list[RuleRagPassage] = []
    metadata_by_rule_id: dict[str, dict[str, Any]] = {}

    for passage in source_passages:
        if selected_community_ids and passage.community_id is not None and passage.community_id not in selected_community_ids:
            continue
        if passage.rule_id is not None and passage.rule_id not in candidate_rule_ids:
            continue
        extra_terms: set[str] = set()
        if passage.rule_id is None and passage.community_id is not None:
            community = next((item for item in index.communities if item.community_id == passage.community_id), None)
            if community is not None:
                extra_terms = set(community.meta_rule.support_terms)
        elif passage.rule_id is not None:
            record = next((item for item in index.records if item.rule_id == passage.rule_id), None)
            if record is not None:
                extra_terms = set(record.support_terms) | set(record.required_input_keys) | set(record.output_keys)
        score, reasons = _passage_score(passage.text, query, extra_terms=extra_terms)
        passages.append(
            RuleRagPassage(
                passage_id=passage.passage_id,
                rule_id=passage.rule_id,
                community_id=passage.community_id,
                meta_rule_id=passage.meta_rule_id,
                passage_type=passage.passage_type,
                text=passage.text,
                score=score,
                reasons=reasons,
                metadata=dict(passage.metadata),
            )
        )

    ranked = sorted(
        passages,
        key=lambda item: (item.score, item.rule_id is None, item.passage_type == "community_report", item.passage_id),
        reverse=True,
    )
    top_passages = [item for item in ranked if item.score > 0][:top_k]
    if not top_passages:
        top_passages = ranked[:top_k]
    if selected_community_ids:
        selected_reports = {
            passage.community_id: passage
            for passage in ranked
            if passage.passage_type == "community_report" and passage.community_id in selected_community_ids
        }
        existing_ids = {item.passage_id for item in top_passages}
        for community_id in sorted(selected_community_ids):
            passage = selected_reports.get(community_id)
            if passage is None or passage.passage_id in existing_ids:
                continue
            top_passages.append(passage)
            existing_ids.add(passage.passage_id)

    for passage in top_passages:
        if not passage.rule_id:
            continue
        slot = metadata_by_rule_id.setdefault(
            passage.rule_id,
            {
                "graph_rag_hits": 0,
                "top_passage_id": passage.passage_id,
                "top_passage_type": passage.passage_type,
                "top_passage_score": passage.score,
                "community_id": passage.community_id,
                "meta_rule_id": passage.meta_rule_id,
            },
        )
        slot["graph_rag_hits"] = int(slot["graph_rag_hits"]) + 1
        if passage.score > int(slot["top_passage_score"]):
            slot["top_passage_id"] = passage.passage_id
            slot["top_passage_type"] = passage.passage_type
            slot["top_passage_score"] = passage.score

    return RuleGraphRagResult(
        passages=top_passages,
        metadata_by_rule_id=metadata_by_rule_id,
        community_reports=[item for item in top_passages if item.passage_type == "community_report"],
        used_fallback=bool(route is not None and route.used_fallback),
    )
