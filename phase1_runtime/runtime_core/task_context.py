from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class ContextFactEntry:
    fact_id: str
    fact_type: str
    value: Any
    status: str
    source: str
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskContext:
    context_id: str
    question_text: str
    scenario_hint: str
    parser_status: str
    context_status: str
    completeness_score: float
    document_refs: list[dict[str, Any]]
    fact_entries: list[ContextFactEntry]
    evidence_packets: list[dict[str, Any]]
    unresolved_slots: list[str] = field(default_factory=list)
    derived_values: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["completeness_score"] = round(self.completeness_score, 4)
        return payload


def _fact_status(item: dict[str, Any]) -> str:
    source = item.get("source")
    status = item.get("status")
    # Signal detection produces explicit status
    if status in {"grounded", "missing", "assumed", "conflicting"}:
        return status
    # Legacy: map source-based status
    if source == "parsed_upload":
        return "grounded"
    if source == "scenario_default":
        return "assumed"
    return "grounded"


def build_task_context(
    *,
    question_text: str,
    scenario_hint: str,
    parser_status: str,
    documents: list[dict[str, Any]],
    fact_sheet: list[dict[str, Any]],
    evidence_packets: list[dict[str, Any]],
    unresolved_slots: list[str] | None = None,
    derived_values: list[dict[str, Any]] | None = None,
    document_chunks: list[dict[str, Any]] | None = None,
) -> TaskContext:
    fact_entries = [
        ContextFactEntry(
            fact_id=str(item.get("fact_id")),
            fact_type=str(item.get("fact_type", "unknown")),
            value=item.get("value"),
            status=_fact_status(item),
            source=str(item.get("source", "unknown")),
            evidence_refs=list(item.get("evidence_refs", [])),
        )
        for item in fact_sheet
    ]
    grounded_count = sum(1 for item in fact_entries if item.status == "grounded")
    assumed_count = sum(1 for item in fact_entries if item.status == "assumed")
    total = len(fact_entries)
    completeness_score = 0.0 if total == 0 else (grounded_count + assumed_count * 0.5) / total
    unresolved = [] if unresolved_slots is None else list(unresolved_slots)
    if not fact_entries:
        context_status = "insufficient_context"
    elif unresolved and grounded_count == 0:
        context_status = "insufficient_context"
    elif unresolved or assumed_count:
        context_status = "partially_grounded"
    else:
        context_status = "grounded_enough"

    document_refs = [
        {
            "doc_id": item.get("doc_id"),
            "title": item.get("title"),
            "doc_type": item.get("doc_type"),
            "parse_status": item.get("parse_status"),
            "source_type": item.get("source_type"),
        }
        for item in documents
    ]

    return TaskContext(
        context_id=f"context_{uuid4().hex[:12]}",
        question_text=question_text,
        scenario_hint=scenario_hint,
        parser_status=parser_status,
        context_status=context_status,
        completeness_score=completeness_score,
        document_refs=document_refs,
        fact_entries=fact_entries,
        evidence_packets=list(evidence_packets),
        unresolved_slots=unresolved,
        derived_values=[] if derived_values is None else list(derived_values),
    )
