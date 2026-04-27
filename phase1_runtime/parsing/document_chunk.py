from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class DocumentChunk:
    chunk_id: str
    doc_id: str
    text: str
    chunk_type: str          # "paragraph" | "table_row" | "heading" | "clause"
    locator: dict[str, Any]  # page, line, sheet, row etc.
    source: str = "upload"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chunks_from_line_items(line_items: list[dict[str, Any]]) -> list[DocumentChunk]:
    """Convert document_parser_mvp line_items to typed DocumentChunk list."""
    chunks: list[DocumentChunk] = []
    for item in line_items:
        text = str(item.get("text", "")).strip()
        if not text or item.get("doc_type") == "question":
            continue
        locator = dict(item.get("locator", {}))
        locator.setdefault("line", item.get("line_no", 1))
        locator.setdefault("source", item.get("source", "upload"))
        chunk_type = _infer_chunk_type(item)
        chunk_id = f"chunk_{item.get('doc_id', 'doc')}_{item.get('line_no', 1)}_{uuid4().hex[:6]}"
        chunks.append(DocumentChunk(
            chunk_id=chunk_id,
            doc_id=str(item.get("doc_id", "unknown")),
            text=text,
            chunk_type=chunk_type,
            locator=locator,
            source=str(item.get("source", "upload")),
        ))
    return chunks


def _infer_chunk_type(item: dict[str, Any]) -> str:
    locator = item.get("locator", {})
    if "sheet" in locator or "row" in locator:
        return "table_row"
    text = str(item.get("text", ""))
    if len(text) < 60 and text.endswith(("：", ":", "。", ".")):
        return "heading"
    if any(kw in text for kw in ("第", "条", "款", "项", "合同约定", "应", "须", "不得")):
        return "clause"
    return "paragraph"
