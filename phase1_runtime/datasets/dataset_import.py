from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..contracts import (
    CaseRecord,
    DocumentBundleRecord,
    ExecutionTraceRecord,
    ReviewTask,
    SimulationDataset,
)
from ..contracts import validate_dataset_dir
from ..schema import QuestionStruct, Rule


class DatasetImportError(ValueError):
    """Raised when a dataset cannot be imported safely."""


@dataclass(slots=True)
class ImportedDataset:
    dataset_dir: Path
    validation_summary: dict[str, Any]
    question: QuestionStruct
    rule_pool: list[Rule]
    execution_trace: ExecutionTraceRecord
    document_bundle: DocumentBundleRecord
    case_record: CaseRecord
    review_task: ReviewTask
    simulation_dataset: SimulationDataset

    def to_summary(self) -> dict[str, Any]:
        return {
            "dataset_dir": str(self.dataset_dir),
            "valid": bool(self.validation_summary.get("valid")),
            "question_text": self.question.question_text,
            "rule_count": len(self.rule_pool),
            "matched_rule_id": self.execution_trace.retrieval.get("matched_rule_id"),
            "trace_id": self.execution_trace.trace_id,
            "dataset_id": self.simulation_dataset.dataset_id,
            "scenario_name": self.simulation_dataset.scenario_name,
        }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_validation_errors(validation_summary: dict[str, Any]) -> str:
    parts: list[str] = []
    for filename, result in validation_summary.get("files", {}).items():
        if result.get("valid", False):
            continue
        issues = result.get("issues", [])
        first_issue = issues[0]["message"] if issues else "unknown issue"
        parts.append(f"{filename}: {first_issue}")
    if not parts:
        return "dataset validation failed"
    return "; ".join(parts)


def import_dataset_dir(dataset_dir: str | Path, require_valid: bool = True) -> ImportedDataset:
    root = Path(dataset_dir)
    validation_summary = validate_dataset_dir(root)
    if require_valid and not validation_summary.get("valid", False):
        raise DatasetImportError(_format_validation_errors(validation_summary))

    question = QuestionStruct.from_dict(_read_json(root / "question_struct.json"))
    rule_pool = [Rule.from_dict(item) for item in _read_json(root / "rule_pool.json")]
    execution_trace = ExecutionTraceRecord.from_dict(_read_json(root / "execution_trace.json"))
    document_bundle = DocumentBundleRecord.from_dict(_read_json(root / "document_bundle.json"))
    case_record = CaseRecord.from_dict(_read_json(root / "case_record.json"))
    review_task = ReviewTask.from_dict(_read_json(root / "review_task.json"))
    simulation_dataset = SimulationDataset.from_dict(_read_json(root / "simulation_dataset.json"))

    return ImportedDataset(
        dataset_dir=root.resolve(),
        validation_summary=validation_summary,
        question=question,
        rule_pool=rule_pool,
        execution_trace=execution_trace,
        document_bundle=document_bundle,
        case_record=case_record,
        review_task=review_task,
        simulation_dataset=simulation_dataset,
    )


if __name__ == "__main__":
    imported = import_dataset_dir("phase1_runtime/sim_data/demo_set_001")
    print(json.dumps(imported.to_summary(), ensure_ascii=False, indent=2))
