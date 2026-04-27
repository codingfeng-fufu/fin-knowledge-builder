from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from ..schema import EvidenceRef, QuestionStruct, Rule


@dataclass(slots=True)
class DocumentRecord:
    doc_id: str
    doc_type: str
    title: str
    language: str
    source: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentRecord":
        return cls(
            doc_id=str(data.get("doc_id")),
            doc_type=str(data.get("doc_type")),
            title=str(data.get("title")),
            language=str(data.get("language")),
            source=str(data.get("source")),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DocumentBundleRecord:
    bundle_id: str
    scenario_id: str
    documents: list[DocumentRecord]
    facts: dict[str, Any]
    evidence_refs: list[EvidenceRef]
    created_at: str
    notes: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentBundleRecord":
        return cls(
            bundle_id=str(data.get("bundle_id")),
            scenario_id=str(data.get("scenario_id")),
            documents=[DocumentRecord.from_dict(item) for item in data.get("documents", [])],
            facts=dict(data.get("facts", {})),
            evidence_refs=[EvidenceRef.from_dict(item) for item in data.get("evidence_refs", [])],
            created_at=str(data.get("created_at")),
            notes=str(data.get("notes")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["documents"] = [item.to_dict() for item in self.documents]
        payload["evidence_refs"] = [item.to_dict() for item in self.evidence_refs]
        return payload


@dataclass(slots=True)
class GoldAnswer:
    answer_text: str
    decision: str
    confidence: float
    explanation: str
    evidence_snippet_ids: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoldAnswer":
        return cls(
            answer_text=str(data.get("answer_text")),
            decision=str(data.get("decision")),
            confidence=float(data.get("confidence")),
            explanation=str(data.get("explanation")),
            evidence_snippet_ids=list(data.get("evidence_snippet_ids", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CaseStep:
    step_id: str
    description: str
    tool: str
    inputs: dict[str, Any]
    expected_output: dict[str, Any]
    evidence_snippet_ids: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseStep":
        return cls(
            step_id=str(data.get("step_id")),
            description=str(data.get("description")),
            tool=str(data.get("tool")),
            inputs=dict(data.get("inputs", {})),
            expected_output=dict(data.get("expected_output", {})),
            evidence_snippet_ids=list(data.get("evidence_snippet_ids", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CaseRecord:
    case_id: str
    scenario_id: str
    title: str
    question: QuestionStruct
    document_bundle_id: str
    gold_answer: GoldAnswer
    solution_steps: list[CaseStep]
    linked_rule_ids: list[str]
    review_status: str
    reviewer: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseRecord":
        return cls(
            case_id=str(data.get("case_id")),
            scenario_id=str(data.get("scenario_id")),
            title=str(data.get("title")),
            question=QuestionStruct.from_dict(dict(data.get("question", {}))),
            document_bundle_id=str(data.get("document_bundle_id")),
            gold_answer=GoldAnswer.from_dict(dict(data.get("gold_answer", {}))),
            solution_steps=[CaseStep.from_dict(item) for item in data.get("solution_steps", [])],
            linked_rule_ids=list(data.get("linked_rule_ids", [])),
            review_status=str(data.get("review_status")),
            reviewer=str(data.get("reviewer")),
            created_at=str(data.get("created_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["question"] = self.question.to_dict()
        payload["gold_answer"] = self.gold_answer.to_dict()
        payload["solution_steps"] = [item.to_dict() for item in self.solution_steps]
        return payload


@dataclass(slots=True)
class ReviewChecklistItem:
    item_id: str
    label: str
    status: str
    note: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewChecklistItem":
        return cls(
            item_id=str(data.get("item_id")),
            label=str(data.get("label")),
            status=str(data.get("status")),
            note=str(data.get("note")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewTask:
    review_task_id: str
    target_type: str
    target_id: str
    status: str
    assignee: str
    checklist: list[ReviewChecklistItem]
    comments: list[str]
    created_at: str
    completed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewTask":
        return cls(
            review_task_id=str(data.get("review_task_id")),
            target_type=str(data.get("target_type")),
            target_id=str(data.get("target_id")),
            status=str(data.get("status")),
            assignee=str(data.get("assignee")),
            checklist=[ReviewChecklistItem.from_dict(item) for item in data.get("checklist", [])],
            comments=list(data.get("comments", [])),
            created_at=str(data.get("created_at")),
            completed_at=data.get("completed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checklist"] = [item.to_dict() for item in self.checklist]
        return payload


@dataclass(slots=True)
class FeedbackRecord:
    feedback_id: str
    trace_id: str
    case_id: str | None
    rule_ids: list[str]
    route_decision: str
    feedback_type: str
    payload: dict[str, Any]
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackRecord":
        return cls(
            feedback_id=str(data.get("feedback_id")),
            trace_id=str(data.get("trace_id")),
            case_id=None if data.get("case_id") is None else str(data.get("case_id")),
            rule_ids=list(data.get("rule_ids", [])),
            route_decision=str(data.get("route_decision")),
            feedback_type=str(data.get("feedback_type")),
            payload=dict(data.get("payload", {})),
            created_at=str(data.get("created_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionTraceRecord:
    trace_id: str
    created_at: str
    route_decision: str
    status: str
    question_struct: dict[str, Any]
    retrieval: dict[str, Any]
    resolved_inputs: dict[str, Any]
    step_contracts: list[dict[str, Any]]
    step_results: list[dict[str, Any]]
    validator_results: list[dict[str, Any]]
    final_result: dict[str, Any] | None
    failure_reason: str | None
    composition_plan: dict[str, Any] | None = None
    composition_trace: dict[str, Any] | None = None
    feedback: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionTraceRecord":
        return cls(
            trace_id=str(data.get("trace_id")),
            created_at=str(data.get("created_at")),
            route_decision=str(data.get("route_decision")),
            status=str(data.get("status")),
            question_struct=dict(data.get("question_struct", {})),
            retrieval=dict(data.get("retrieval", {})),
            resolved_inputs=dict(data.get("resolved_inputs", {})),
            step_contracts=list(data.get("step_contracts", [])),
            step_results=list(data.get("step_results", [])),
            validator_results=list(data.get("validator_results", [])),
            final_result=data.get("final_result"),
            failure_reason=data.get("failure_reason"),
            composition_plan=data.get("composition_plan"),
            composition_trace=data.get("composition_trace"),
            feedback=list(data.get("feedback", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SimulationDataset:
    dataset_id: str
    scenario_name: str
    generated_at: str
    question: QuestionStruct
    document_bundle: DocumentBundleRecord
    case_record: CaseRecord
    rule_pool: list[Rule]
    review_task: ReviewTask
    execution_trace: ExecutionTraceRecord

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulationDataset":
        return cls(
            dataset_id=str(data.get("dataset_id")),
            scenario_name=str(data.get("scenario_name")),
            generated_at=str(data.get("generated_at")),
            question=QuestionStruct.from_dict(dict(data.get("question", {}))),
            document_bundle=DocumentBundleRecord.from_dict(dict(data.get("document_bundle", {}))),
            case_record=CaseRecord.from_dict(dict(data.get("case_record", {}))),
            rule_pool=[Rule.from_dict(item) for item in data.get("rule_pool", [])],
            review_task=ReviewTask.from_dict(dict(data.get("review_task", {}))),
            execution_trace=ExecutionTraceRecord.from_dict(dict(data.get("execution_trace", {}))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "scenario_name": self.scenario_name,
            "generated_at": self.generated_at,
            "question": self.question.to_dict(),
            "document_bundle": self.document_bundle.to_dict(),
            "case_record": self.case_record.to_dict(),
            "rule_pool": [rule.to_dict() for rule in self.rule_pool],
            "review_task": self.review_task.to_dict(),
            "execution_trace": self.execution_trace.to_dict(),
        }

    def write_to_dir(self, output_dir: str | Path) -> dict[str, str]:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)

        files = {
            "dataset": root / "simulation_dataset.json",
            "question": root / "question_struct.json",
            "document_bundle": root / "document_bundle.json",
            "case_record": root / "case_record.json",
            "rule_pool": root / "rule_pool.json",
            "review_task": root / "review_task.json",
            "execution_trace": root / "execution_trace.json",
            "manifest": root / "dataset_manifest.json",
        }

        write_json(files["dataset"], self.to_dict())
        write_json(files["question"], self.question.to_dict())
        write_json(files["document_bundle"], self.document_bundle.to_dict())
        write_json(files["case_record"], self.case_record.to_dict())
        write_json(files["rule_pool"], [rule.to_dict() for rule in self.rule_pool])
        write_json(files["review_task"], self.review_task.to_dict())
        write_json(files["execution_trace"], self.execution_trace.to_dict())
        write_json(
            files["manifest"],
            {
                "dataset_id": self.dataset_id,
                "scenario_name": self.scenario_name,
                "generated_at": self.generated_at,
                "files": {key: str(path.name) for key, path in files.items()},
            },
        )
        return {key: str(path) for key, path in files.items()}


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
