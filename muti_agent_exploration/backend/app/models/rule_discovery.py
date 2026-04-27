"""
规则发现相关数据模型与持久化管理。
"""

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..config import Config


def _now_iso() -> str:
    return datetime.now().isoformat()


def _write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, dir=os.path.dirname(path)) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    os.replace(temp_path, path)


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class DiscoveryTaskStatus(str, Enum):
    RECEIVED = "received"
    FRAMED = "framed"
    ANALOGIES_FOUND = "analogies_found"
    EVIDENCE_COLLECTED = "evidence_collected"
    CANDIDATES_PROPOSED = "candidates_proposed"
    CANDIDATES_VALIDATED = "candidates_validated"
    DECIDED = "decided"
    COMPLETED = "completed"
    FAILED = "failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEED_HUMAN_REVIEW = "need_human_review"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class CandidateType(str, Enum):
    EXACT_REUSE = "exact_reuse"
    ADAPTED_RULE = "adapted_rule"
    NOVEL_RULE = "novel_rule"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    SUPPORTED = "supported"
    PROVISIONALLY_SUPPORTED = "provisionally_supported"
    WEAKLY_SUPPORTED = "weakly_supported"
    REJECTED = "rejected"
    NEED_HUMAN_REVIEW = "need_human_review"


class ResolutionType(str, Enum):
    EXACT_REUSE = "exact_reuse"
    ADAPTED_RULE = "adapted_rule"
    NOVEL_RULE = "novel_rule"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class DiscoveryMode(str, Enum):
    GROUNDED = "grounded"
    EMERGENT = "emergent"


@dataclass
class RuleRecord:
    rule_id: str
    title: str
    content: str
    conditions: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    priority: int = 0
    source: str = ""
    tags: List[str] = field(default_factory=list)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "content": self.content,
            "conditions": self.conditions,
            "exceptions": self.exceptions,
            "priority": self.priority,
            "source": self.source,
            "tags": self.tags,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuleRecord":
        return cls(
            rule_id=data["rule_id"],
            title=data.get("title", ""),
            content=data.get("content", ""),
            conditions=data.get("conditions", []) or [],
            exceptions=data.get("exceptions", []) or [],
            priority=int(data.get("priority", 0) or 0),
            source=data.get("source", ""),
            tags=data.get("tags", []) or [],
            status=data.get("status", "active"),
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class RuleSet:
    rule_set_id: str
    name: str
    description: str = ""
    rules: List[RuleRecord] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_set_id": self.rule_set_id,
            "name": self.name,
            "description": self.description,
            "rules": [rule.to_dict() for rule in self.rules],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuleSet":
        return cls(
            rule_set_id=data["rule_set_id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            rules=[RuleRecord.from_dict(item) for item in data.get("rules", []) or []],
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    content: str
    index: int
    source_name: str
    start_offset: int = 0
    end_offset: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "index": self.index,
            "source_name": self.source_name,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentChunk":
        return cls(
            chunk_id=data["chunk_id"],
            document_id=data["document_id"],
            content=data.get("content", ""),
            index=int(data.get("index", 0) or 0),
            source_name=data.get("source_name", ""),
            start_offset=int(data.get("start_offset", 0) or 0),
            end_offset=int(data.get("end_offset", 0) or 0),
            metadata=data.get("metadata", {}) or {},
        )

    @property
    def reference(self) -> str:
        return f"{self.document_id}#chunk_{self.index}"


@dataclass
class DocumentRecord:
    document_id: str
    filename: str
    original_filename: str
    path: str
    size: int
    chunk_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "path": self.path,
            "size": self.size,
            "chunk_ids": self.chunk_ids,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentRecord":
        return cls(
            document_id=data["document_id"],
            filename=data.get("filename", ""),
            original_filename=data.get("original_filename", ""),
            path=data.get("path", ""),
            size=int(data.get("size", 0) or 0),
            chunk_ids=data.get("chunk_ids", []) or [],
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class DocumentSet:
    document_set_id: str
    name: str
    description: str = ""
    documents: List[DocumentRecord] = field(default_factory=list)
    chunks: List[DocumentChunk] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_set_id": self.document_set_id,
            "name": self.name,
            "description": self.description,
            "documents": [doc.to_dict() for doc in self.documents],
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentSet":
        return cls(
            document_set_id=data["document_set_id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            documents=[DocumentRecord.from_dict(item) for item in data.get("documents", []) or []],
            chunks=[DocumentChunk.from_dict(item) for item in data.get("chunks", []) or []],
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class CandidateRule:
    candidate_id: str
    candidate_type: CandidateType
    rule_text: str
    rule_title: str = ""
    rule_id: Optional[str] = None
    derived_from: List[str] = field(default_factory=list)
    adaptation_note: str = ""
    why_applicable: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    knowledge_sources: List[str] = field(default_factory=list)
    source_provenance: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    grounding_score: float = 0.0
    speculation_score: float = 0.0
    validation_status: ValidationStatus = ValidationStatus.PENDING
    validation_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type.value,
            "rule_text": self.rule_text,
            "rule_title": self.rule_title,
            "rule_id": self.rule_id,
            "derived_from": self.derived_from,
            "adaptation_note": self.adaptation_note,
            "why_applicable": self.why_applicable,
            "evidence_refs": self.evidence_refs,
            "knowledge_sources": self.knowledge_sources,
            "source_provenance": self.source_provenance,
            "confidence": self.confidence,
            "grounding_score": self.grounding_score,
            "speculation_score": self.speculation_score,
            "validation_status": self.validation_status.value,
            "validation_reason": self.validation_reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateRule":
        return cls(
            candidate_id=data["candidate_id"],
            candidate_type=CandidateType(data.get("candidate_type", CandidateType.NOVEL_RULE.value)),
            rule_text=data.get("rule_text", ""),
            rule_title=data.get("rule_title", ""),
            rule_id=data.get("rule_id"),
            derived_from=data.get("derived_from", []) or [],
            adaptation_note=data.get("adaptation_note", ""),
            why_applicable=data.get("why_applicable", ""),
            evidence_refs=data.get("evidence_refs", []) or [],
            knowledge_sources=data.get("knowledge_sources", []) or [],
            source_provenance=data.get("source_provenance", {}) or {},
            confidence=float(data.get("confidence", 0.0) or 0.0),
            grounding_score=float(data.get("grounding_score", 0.0) or 0.0),
            speculation_score=float(data.get("speculation_score", 0.0) or 0.0),
            validation_status=ValidationStatus(data.get("validation_status", ValidationStatus.PENDING.value)),
            validation_reason=data.get("validation_reason", ""),
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class DiscoveryTask:
    task_id: str
    query: str
    context: str
    rule_set_id: str
    discovery_mode: DiscoveryMode = DiscoveryMode.GROUNDED
    document_set_id: Optional[str] = None
    status: DiscoveryTaskStatus = DiscoveryTaskStatus.RECEIVED
    progress: int = 0
    current_stage: str = "received"
    error: Optional[str] = None
    cancel_requested: bool = False
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: str = field(default_factory=_now_iso)
    attempt_count: int = 1
    parent_task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "query": self.query,
            "context": self.context,
            "rule_set_id": self.rule_set_id,
            "discovery_mode": self.discovery_mode.value,
            "document_set_id": self.document_set_id,
            "status": self.status.value,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "updated_at": self.updated_at,
            "attempt_count": self.attempt_count,
            "parent_task_id": self.parent_task_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryTask":
        return cls(
            task_id=data["task_id"],
            query=data.get("query", ""),
            context=data.get("context", ""),
            rule_set_id=data.get("rule_set_id", ""),
            discovery_mode=DiscoveryMode(data.get("discovery_mode", DiscoveryMode.GROUNDED.value)),
            document_set_id=data.get("document_set_id"),
            status=DiscoveryTaskStatus(data.get("status", DiscoveryTaskStatus.RECEIVED.value)),
            progress=int(data.get("progress", 0) or 0),
            current_stage=data.get("current_stage", "received"),
            error=data.get("error"),
            cancel_requested=bool(data.get("cancel_requested", False)),
            created_at=data.get("created_at", _now_iso()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            updated_at=data.get("updated_at", _now_iso()),
            attempt_count=int(data.get("attempt_count", 1) or 1),
            parent_task_id=data.get("parent_task_id"),
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class DiscoveryDecision:
    resolution_type: ResolutionType
    discovery_mode: DiscoveryMode = DiscoveryMode.GROUNDED
    candidate_rules: List[CandidateRule] = field(default_factory=list)
    rejected_candidates: List[Dict[str, Any]] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    summary: str = ""
    need_human_review: bool = False
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolution_type": self.resolution_type.value,
            "discovery_mode": self.discovery_mode.value,
            "candidate_rules": [item.to_dict() for item in self.candidate_rules],
            "rejected_candidates": self.rejected_candidates,
            "open_questions": self.open_questions,
            "summary": self.summary,
            "need_human_review": self.need_human_review,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryDecision":
        return cls(
            resolution_type=ResolutionType(data.get("resolution_type", ResolutionType.INSUFFICIENT_EVIDENCE.value)),
            discovery_mode=DiscoveryMode(data.get("discovery_mode", DiscoveryMode.GROUNDED.value)),
            candidate_rules=[CandidateRule.from_dict(item) for item in data.get("candidate_rules", []) or []],
            rejected_candidates=data.get("rejected_candidates", []) or [],
            open_questions=data.get("open_questions", []) or [],
            summary=data.get("summary", ""),
            need_human_review=bool(data.get("need_human_review", False)),
            created_at=data.get("created_at", _now_iso()),
        )


class RuleDiscoveryPaths:
    ROOT_DIR = os.path.join(Config.UPLOAD_FOLDER, 'rule_discovery')
    RULE_SETS_DIR = os.path.join(ROOT_DIR, 'rule_sets')
    DOCUMENT_SETS_DIR = os.path.join(ROOT_DIR, 'document_sets')
    TASKS_DIR = os.path.join(ROOT_DIR, 'tasks')


class RuleSetManager:
    @classmethod
    def _ensure_dir(cls) -> None:
        os.makedirs(RuleDiscoveryPaths.RULE_SETS_DIR, exist_ok=True)

    @classmethod
    def _get_rule_set_dir(cls, rule_set_id: str) -> str:
        return os.path.join(RuleDiscoveryPaths.RULE_SETS_DIR, rule_set_id)

    @classmethod
    def _get_rule_set_path(cls, rule_set_id: str) -> str:
        return os.path.join(cls._get_rule_set_dir(rule_set_id), 'rule_set.json')

    @classmethod
    def create_rule_set(
        cls,
        name: str,
        rules: List[RuleRecord],
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RuleSet:
        cls._ensure_dir()
        rule_set = RuleSet(
            rule_set_id=f"rules_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            rules=rules,
            metadata=metadata or {},
        )
        cls.save_rule_set(rule_set)
        return rule_set

    @classmethod
    def save_rule_set(cls, rule_set: RuleSet) -> None:
        rule_set.updated_at = _now_iso()
        _write_json(cls._get_rule_set_path(rule_set.rule_set_id), rule_set.to_dict())

    @classmethod
    def get_rule_set(cls, rule_set_id: str) -> Optional[RuleSet]:
        data = _read_json(cls._get_rule_set_path(rule_set_id))
        if not data:
            return None
        return RuleSet.from_dict(data)

    @classmethod
    def list_rule_sets(cls, limit: int = 50) -> List[RuleSet]:
        cls._ensure_dir()
        results: List[RuleSet] = []
        for rule_set_id in os.listdir(RuleDiscoveryPaths.RULE_SETS_DIR):
            rule_set = cls.get_rule_set(rule_set_id)
            if rule_set:
                results.append(rule_set)
        results.sort(key=lambda item: item.created_at, reverse=True)
        return results[:limit]


class DocumentStoreManager:
    @classmethod
    def _ensure_dir(cls) -> None:
        os.makedirs(RuleDiscoveryPaths.DOCUMENT_SETS_DIR, exist_ok=True)

    @classmethod
    def _get_document_set_dir(cls, document_set_id: str) -> str:
        return os.path.join(RuleDiscoveryPaths.DOCUMENT_SETS_DIR, document_set_id)

    @classmethod
    def _get_document_set_path(cls, document_set_id: str) -> str:
        return os.path.join(cls._get_document_set_dir(document_set_id), 'document_set.json')

    @classmethod
    def _get_files_dir(cls, document_set_id: str) -> str:
        return os.path.join(cls._get_document_set_dir(document_set_id), 'files')

    @classmethod
    def create_document_set(
        cls,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentSet:
        cls._ensure_dir()
        document_set = DocumentSet(
            document_set_id=f"docs_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            metadata=metadata or {},
        )
        cls.save_document_set(document_set)
        return document_set

    @classmethod
    def save_document_set(cls, document_set: DocumentSet) -> None:
        document_set.updated_at = _now_iso()
        _write_json(cls._get_document_set_path(document_set.document_set_id), document_set.to_dict())

    @classmethod
    def get_document_set(cls, document_set_id: str) -> Optional[DocumentSet]:
        data = _read_json(cls._get_document_set_path(document_set_id))
        if not data:
            return None
        return DocumentSet.from_dict(data)

    @classmethod
    def list_document_sets(cls, limit: int = 50) -> List[DocumentSet]:
        cls._ensure_dir()
        results: List[DocumentSet] = []
        for document_set_id in os.listdir(RuleDiscoveryPaths.DOCUMENT_SETS_DIR):
            document_set = cls.get_document_set(document_set_id)
            if document_set:
                results.append(document_set)
        results.sort(key=lambda item: item.created_at, reverse=True)
        return results[:limit]

    @classmethod
    def add_uploaded_document(
        cls,
        document_set_id: str,
        file_storage: Any,
        chunks: List[DocumentChunk],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentRecord:
        document_set = cls.get_document_set(document_set_id)
        if not document_set:
            raise ValueError(f"文档集不存在: {document_set_id}")

        original_filename = file_storage.filename or "document.txt"
        ext = os.path.splitext(original_filename)[1].lower()
        filename = f"{uuid.uuid4().hex[:10]}{ext}"
        files_dir = cls._get_files_dir(document_set_id)
        os.makedirs(files_dir, exist_ok=True)
        path = os.path.join(files_dir, filename)
        file_storage.save(path)

        document_id = f"doc_{uuid.uuid4().hex[:12]}"
        normalized_chunks: List[DocumentChunk] = []
        for index, chunk in enumerate(chunks):
            normalized_chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}_chunk_{index}",
                    document_id=document_id,
                    content=chunk.content,
                    index=index,
                    source_name=original_filename,
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    metadata=chunk.metadata,
                )
            )

        document = DocumentRecord(
            document_id=document_id,
            filename=filename,
            original_filename=original_filename,
            path=path,
            size=os.path.getsize(path),
            chunk_ids=[chunk.chunk_id for chunk in normalized_chunks],
            metadata=metadata or {},
        )
        document_set.documents.append(document)
        document_set.chunks.extend(normalized_chunks)
        cls.save_document_set(document_set)
        return document

    @classmethod
    def add_text_document(
        cls,
        document_set_id: str,
        title: str,
        raw_text: str,
        chunks: List[DocumentChunk],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentRecord:
        document_set = cls.get_document_set(document_set_id)
        if not document_set:
            raise ValueError(f"文档集不存在: {document_set_id}")

        files_dir = cls._get_files_dir(document_set_id)
        os.makedirs(files_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex[:10]}.txt"
        path = os.path.join(files_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(raw_text)

        document_id = f"doc_{uuid.uuid4().hex[:12]}"
        normalized_chunks: List[DocumentChunk] = []
        for index, chunk in enumerate(chunks):
            normalized_chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}_chunk_{index}",
                    document_id=document_id,
                    content=chunk.content,
                    index=index,
                    source_name=title,
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    metadata=chunk.metadata,
                )
            )

        document = DocumentRecord(
            document_id=document_id,
            filename=filename,
            original_filename=title,
            path=path,
            size=os.path.getsize(path),
            chunk_ids=[chunk.chunk_id for chunk in normalized_chunks],
            metadata=metadata or {},
        )
        document_set.documents.append(document)
        document_set.chunks.extend(normalized_chunks)
        cls.save_document_set(document_set)
        return document


class RuleDiscoveryTaskManager:
    @classmethod
    def _ensure_dir(cls) -> None:
        os.makedirs(RuleDiscoveryPaths.TASKS_DIR, exist_ok=True)

    @classmethod
    def _get_task_dir(cls, task_id: str) -> str:
        return os.path.join(RuleDiscoveryPaths.TASKS_DIR, task_id)

    @classmethod
    def _get_task_path(cls, task_id: str) -> str:
        return os.path.join(cls._get_task_dir(task_id), 'task.json')

    @classmethod
    def _get_result_path(cls, task_id: str) -> str:
        return os.path.join(cls._get_task_dir(task_id), 'result.json')

    @classmethod
    def _get_logs_path(cls, task_id: str) -> str:
        return os.path.join(cls._get_task_dir(task_id), 'logs.jsonl')

    @classmethod
    def _get_stage_dir(cls, task_id: str) -> str:
        return os.path.join(cls._get_task_dir(task_id), 'stages')

    @classmethod
    def _get_stage_path(cls, task_id: str, stage: str) -> str:
        return os.path.join(cls._get_stage_dir(task_id), f'{stage}.json')

    @classmethod
    def create_task(
        cls,
        query: str,
        context: str,
        rule_set_id: str,
        discovery_mode: DiscoveryMode = DiscoveryMode.GROUNDED,
        document_set_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        attempt_count: int = 1,
    ) -> DiscoveryTask:
        cls._ensure_dir()
        task = DiscoveryTask(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            query=query,
            context=context,
            rule_set_id=rule_set_id,
            discovery_mode=discovery_mode,
            document_set_id=document_set_id,
            parent_task_id=parent_task_id,
            attempt_count=attempt_count,
            metadata=metadata or {},
        )
        cls.save_task(task)
        return task

    @classmethod
    def save_task(cls, task: DiscoveryTask) -> None:
        task.updated_at = _now_iso()
        _write_json(cls._get_task_path(task.task_id), task.to_dict())

    @classmethod
    def get_task(cls, task_id: str) -> Optional[DiscoveryTask]:
        data = _read_json(cls._get_task_path(task_id))
        if not data:
            return None
        return DiscoveryTask.from_dict(data)

    @classmethod
    def list_tasks(cls, limit: int = 50) -> List[DiscoveryTask]:
        cls._ensure_dir()
        results: List[DiscoveryTask] = []
        for task_id in os.listdir(RuleDiscoveryPaths.TASKS_DIR):
            task = cls.get_task(task_id)
            if task:
                results.append(task)
        results.sort(key=lambda item: item.created_at, reverse=True)
        return results[:limit]

    @classmethod
    def update_task(
        cls,
        task_id: str,
        *,
        status: Optional[DiscoveryTaskStatus] = None,
        progress: Optional[int] = None,
        current_stage: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cancel_requested: Optional[bool] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> Optional[DiscoveryTask]:
        task = cls.get_task(task_id)
        if not task:
            return None
        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = progress
        if current_stage is not None:
            task.current_stage = current_stage
        if error is not None:
            task.error = error
        if metadata is not None:
            task.metadata = metadata
        if cancel_requested is not None:
            task.cancel_requested = cancel_requested
        if started_at is not None:
            task.started_at = started_at
        if completed_at is not None:
            task.completed_at = completed_at
        cls.save_task(task)
        return task

    @classmethod
    def save_stage_payload(cls, task_id: str, stage: str, payload: Dict[str, Any]) -> None:
        _write_json(cls._get_stage_path(task_id, stage), payload)

    @classmethod
    def get_stage_payload(cls, task_id: str, stage: str) -> Optional[Dict[str, Any]]:
        return _read_json(cls._get_stage_path(task_id, stage))

    @classmethod
    def list_stage_names(cls, task_id: str) -> List[str]:
        stage_dir = cls._get_stage_dir(task_id)
        if not os.path.isdir(stage_dir):
            return []
        names = []
        for filename in os.listdir(stage_dir):
            if not filename.endswith('.json'):
                continue
            names.append(filename[:-5])
        return sorted(names)

    @classmethod
    def append_log(
        cls,
        task_id: str,
        stage: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        level: str = "info",
    ) -> None:
        os.makedirs(cls._get_task_dir(task_id), exist_ok=True)
        entry = {
            "timestamp": _now_iso(),
            "stage": stage,
            "level": level,
            "message": message,
            "payload": payload or {},
        }
        with open(cls._get_logs_path(task_id), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    @classmethod
    def get_logs(cls, task_id: str) -> List[Dict[str, Any]]:
        path = cls._get_logs_path(task_id)
        if not os.path.exists(path):
            return []
        logs: List[Dict[str, Any]] = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return logs

    @classmethod
    def save_result(cls, task_id: str, decision: DiscoveryDecision) -> None:
        _write_json(cls._get_result_path(task_id), decision.to_dict())

    @classmethod
    def get_result(cls, task_id: str) -> Optional[DiscoveryDecision]:
        data = _read_json(cls._get_result_path(task_id))
        if not data:
            return None
        return DiscoveryDecision.from_dict(data)

    @classmethod
    def request_cancel(cls, task_id: str) -> Optional[DiscoveryTask]:
        return cls.update_task(task_id, cancel_requested=True)

    @classmethod
    def find_similar_active_task(
        cls,
        query: str,
        context: str,
        rule_set_id: str,
        discovery_mode: DiscoveryMode,
        document_set_id: Optional[str],
        use_llm: bool,
    ) -> Optional[DiscoveryTask]:
        active_statuses = {
            DiscoveryTaskStatus.RECEIVED,
            DiscoveryTaskStatus.FRAMED,
            DiscoveryTaskStatus.ANALOGIES_FOUND,
            DiscoveryTaskStatus.EVIDENCE_COLLECTED,
            DiscoveryTaskStatus.CANDIDATES_PROPOSED,
            DiscoveryTaskStatus.CANDIDATES_VALIDATED,
            DiscoveryTaskStatus.DECIDED,
        }
        for task in cls.list_tasks(limit=200):
            if task.status not in active_statuses:
                continue
            if task.query != query or task.context != context:
                continue
            if task.rule_set_id != rule_set_id or task.document_set_id != document_set_id:
                continue
            if task.discovery_mode != discovery_mode:
                continue
            if bool(task.metadata.get('use_llm', False)) != bool(use_llm):
                continue
            if task.cancel_requested:
                continue
            return task
        return None
