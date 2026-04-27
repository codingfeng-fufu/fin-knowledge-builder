from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..schema import EvidenceRef, InputField, QuestionStruct
from .document_chunk import DocumentChunk, chunks_from_line_items
from .query_context_builder import build_query_context


QUESTION_DOC_ID = "question_input"


def _guess_document_type(
    name: str,
    content: str,
    default_doc_type: str = "contract",
    explicit_doc_type: str | None = None,
) -> str:
    if explicit_doc_type:
        return explicit_doc_type
    lowered_name = name.lower()
    if "contract" in lowered_name or "合同" in content:
        return "contract"
    if "policy" in lowered_name or "制度" in content or "规则" in content:
        return "policy"
    if "schedule" in lowered_name or "还款计划" in content:
        return "schedule"
    if "report" in lowered_name or "净值报告" in content or "报告" in content:
        return "report"
    return default_doc_type


def _line_items(
    question_text: str,
    materials: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "doc_id": QUESTION_DOC_ID,
            "title": "问题输入",
            "doc_type": "question",
            "line_no": 1,
            "text": question_text.strip(),
            "source": "question",
            "locator": {"line": 1, "source": "question"},
        }
    ]
    for index, material in enumerate(materials, start=1):
        doc_id = material.get("doc_id") or f"upload_doc_{index:03d}"
        content = str(material.get("content", ""))
        doc_type = _guess_document_type(
            str(material.get("name", f"material_{index}")),
            content,
            explicit_doc_type=material.get("doc_type"),
        )
        line_items = material.get("line_items")
        if isinstance(line_items, list) and line_items:
            for line_no, line_item in enumerate(line_items, start=1):
                text_value = str(line_item.get("text", "")).strip()
                if not text_value:
                    continue
                locator = dict(line_item.get("locator", {}))
                locator.setdefault("line", line_item.get("line_no", line_no))
                locator.setdefault("source", line_item.get("source", "upload"))
                items.append(
                    {
                        "doc_id": line_item.get("doc_id", doc_id),
                        "title": line_item.get("title", material.get("name", f"material_{index}")),
                        "doc_type": line_item.get("doc_type", doc_type),
                        "line_no": line_item.get("line_no", line_no),
                        "text": text_value,
                        "source": line_item.get("source", "upload"),
                        "locator": locator,
                    }
                )
            continue

        lines = [line.strip() for line in content.replace("\r", "\n").split("\n") if line.strip()]
        if not lines and content.strip():
            lines = [content.strip()]
        for line_no, line in enumerate(lines, start=1):
            items.append(
                {
                    "doc_id": doc_id,
                    "title": material.get("name", f"material_{index}"),
                    "doc_type": doc_type,
                    "line_no": line_no,
                    "text": line,
                    "source": "upload",
                    "locator": {"line": line_no, "source": "upload"},
                }
            )
    return items


def _build_document_preview(materials: list[dict[str, Any]]) -> dict[str, Any]:
    documents = []
    for index, material in enumerate(materials, start=1):
        content = str(material.get("content", ""))
        documents.append(
            {
                "doc_id": material.get("doc_id") or f"upload_doc_{index:03d}",
                "title": material.get("title") or material.get("name") or f"material_{index}",
                "doc_type": _guess_document_type(
                    str(material.get("name", f"material_{index}")),
                    content,
                    explicit_doc_type=material.get("doc_type"),
                ),
                "source_type": material.get("source_type", "uploaded_text"),
                "parse_status": material.get("parse_status", "parsed_from_upload"),
                "char_count": material.get("char_count", len(content)),
                "line_count": material.get("line_count", len([l for l in content.replace("\r", "\n").split("\n") if l.strip()])),
                "warnings": list(material.get("warnings", [])),
            }
        )
    return {
        "document_count": len(documents),
        "documents": documents,
    }


def parse_workspace_bundle(
    *,
    question_text: str,
    materials: list[dict[str, Any]],
    scenario_id: str,
    seed_question: QuestionStruct,
    seed_facts: dict[str, Any],
    seed_evidence_refs: list[EvidenceRef],
    required_inputs: list[InputField] | None = None,
) -> dict[str, Any]:
    """
    Parse uploaded materials into DocumentChunks and detect signals for routing.

    Instead of regex extraction, this function:
    1. Converts materials into typed DocumentChunks
    2. Runs signal detection against required_inputs hints
    3. Builds fact_sheet with grounded/missing status based on signals
    4. Returns empty facts dict (values extracted at execution time by Agent)
    """
    line_items = _line_items(question_text, materials)
    document_chunks = chunks_from_line_items(line_items)

    # Build QuestionStruct from seed (question_types/intents come from seed)
    doc_types = sorted({
        item["doc_type"]
        for item in line_items
        if item["doc_type"] != "question"
    } or set(seed_question.document_types))

    question_packet = QuestionStruct(
        question_text=question_text,
        question_types=list(seed_question.question_types),
        intents=list(seed_question.intents),
        document_types=doc_types,
        extracted_inputs={},
    )

    question_type = (
        "decision_query"
        if any(token in question_text for token in ["是否", "需不需要", "要不要", "是否需要"])
        else "analysis_query"
    )
    question_packet_preview = question_packet.to_dict()
    question_packet_preview["question_type"] = question_type
    question_packet_preview["scenario_hint"] = scenario_id
    question_packet_preview["target_object"] = scenario_id

    document_preview = _build_document_preview(materials)
    documents = document_preview["documents"]

    effective_inputs = required_inputs or []
    context_packet = build_query_context(
        question_text=question_text,
        document_chunks=[chunk.to_dict() for chunk in document_chunks],
        required_inputs=effective_inputs,
        documents=documents,
    )
    fact_sheet = [
        {
            "fact_id": candidate["fact_id"],
            "fact_type": candidate["fact_type"],
            "value": None,
            "status": candidate["status"],
            "source": "query_context",
            "evidence_refs": list(candidate["evidence_refs"]),
        }
        for candidate in context_packet["fact_candidates"]
    ]
    missing_fact_keys = list(context_packet["context_gaps"])

    has_uploaded_materials = bool(materials)
    if not has_uploaded_materials:
        parser_status = "no_materials"
    elif missing_fact_keys:
        parser_status = "parsed_with_gaps"
    else:
        parser_status = "parsed_complete"

    evidence_refs = [
        EvidenceRef.from_dict(
            {
                "doc_id": item["doc_id"],
                "snippet_id": item["snippet_id"],
                "locator": dict(item["locator"]),
                "text": item["text"],
            }
        )
        for item in context_packet["evidence_units"]
    ]
    evidence_packets = [
        {
            "doc_id": item["doc_id"],
            "snippet_id": item["snippet_id"],
            "text": item["text"],
            "locator": dict(item["locator"]),
            "chunk_type": item.get("chunk_type"),
            "relevance_score": item.get("relevance_score", 0),
        }
        for item in context_packet["evidence_units"]
    ]

    return {
        "question": question_packet,
        "question_packet_preview": question_packet_preview,
        "facts": {},                          # No pre-extraction; Agent extracts at execution time
        "fact_sheet": fact_sheet,
        "missing_fact_keys": missing_fact_keys,
        "documents": documents,
        "document_packet_preview": document_preview,
        "evidence_refs": evidence_refs,
        "evidence_packets": evidence_packets,
        "document_chunks": [chunk.to_dict() for chunk in document_chunks],
        "context_packet": context_packet,
        "parser_status": parser_status,
    }
