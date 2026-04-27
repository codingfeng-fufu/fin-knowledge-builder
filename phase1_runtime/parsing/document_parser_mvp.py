from __future__ import annotations

from base64 import b64decode
from io import BytesIO
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
import zipfile
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import openpyxl

from .pdf_understanding import understand_pdf_bytes


SUPPORTED_EXTENSIONS = {"txt", "md", "json", "csv", "log", "html", "htm", "pdf", "docx", "xlsx"}
TEXT_EXTENSIONS = {"txt", "md", "json", "csv", "log", "html", "htm"}
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _extension(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or "txt"


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _material_bytes(item: dict[str, Any]) -> bytes:
    if item.get("content_base64"):
        return b64decode(str(item["content_base64"]))
    return str(item.get("content", "")).encode("utf-8")


def _guess_doc_type(name: str, text: str, scenario_id: str) -> str:
    lowered_name = name.lower()
    if "contract" in lowered_name or "合同" in text:
        return "contract"
    if "policy" in lowered_name or "制度" in text or "规则" in text:
        return "policy"
    if "schedule" in lowered_name or "还款计划" in text:
        return "schedule"
    if "report" in lowered_name or "净值报告" in text or "报告" in text:
        return "report"
    if "sheet" in lowered_name or "xlsx" in lowered_name:
        return "table"
    if scenario_id == "credit_notice":
        return "contract"
    return "contract"


def _build_result(*, index: int, name: str, scenario_id: str, source_type: str, parse_status: str, text: str, line_items: list[dict[str, Any]], warnings: list[str] | None = None) -> dict[str, Any]:
    doc_id = f"upload_doc_{index:03d}"
    doc_type = _guess_doc_type(name, text, scenario_id)
    normalized_lines = [item for item in line_items if item.get("text")]
    for line_no, item in enumerate(normalized_lines, start=1):
        if not item.get("doc_id"):
            item["doc_id"] = doc_id
        if not item.get("title"):
            item["title"] = name
        if not item.get("doc_type"):
            item["doc_type"] = doc_type
        if not item.get("line_no"):
            item["line_no"] = line_no
        if not item.get("source"):
            item["source"] = "upload"
        if not item.get("locator"):
            item["locator"] = {"line": line_no, "source": "upload"}
    return {
        "name": name,
        "doc_id": doc_id,
        "title": name,
        "doc_type": doc_type,
        "source_type": source_type,
        "parse_status": parse_status,
        "content": text,
        "char_count": len(text),
        "line_count": len(normalized_lines),
        "warnings": [] if warnings is None else warnings,
        "line_items": normalized_lines,
    }


def _parse_text_material(index: int, item: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    name = str(item.get("name") or f"material_{index}")
    ext = _extension(name)
    raw = _material_bytes(item)
    text = _decode_text(raw)
    if ext == "json":
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    elif ext in {"html", "htm"}:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    line_items = [
        {
            "text": line,
            "locator": {"line": line_no, "source": "upload", "format": ext},
        }
        for line_no, line in enumerate(lines, start=1)
    ]
    return _build_result(
        index=index,
        name=name,
        scenario_id=scenario_id,
        source_type="uploaded_text",
        parse_status=f"parsed_{ext}",
        text=text,
        line_items=line_items,
    )


def _parse_pdf_material(index: int, item: dict[str, Any], scenario_id: str, question_text: str | None = None) -> dict[str, Any]:
    name = str(item.get("name") or f"material_{index}.pdf")
    raw = _material_bytes(item)
    try:
        understood = understand_pdf_bytes(raw, query_text=question_text)
    except Exception as exc:
        return _parse_error_material(index, item, scenario_id, exc)

    title = understood.get("title") or name
    document_family = str(understood.get("document_family") or "")
    blocks = list(understood.get("blocks") or [])
    line_items = [
        {
            "text": block["text"],
            "doc_type": "report" if document_family.endswith("report") else None,
            "title": title,
            "locator": {
                "page": block.get("page") or 1,
                "source": "upload",
                "format": "pdf",
                "section": block.get("section"),
                "block_type": block.get("block_type"),
            },
        }
        for block in blocks
    ]
    text = "\n".join(block["text"] for block in blocks if block.get("text"))
    parse_status = "parsed_pdf_kimi" if text else "parse_error"
    warnings = None if text else ["pdf understanding returned no usable blocks"]

    result = _build_result(
        index=index,
        name=name,
        scenario_id=scenario_id,
        source_type="uploaded_pdf",
        parse_status=parse_status,
        text=text,
        line_items=line_items,
        warnings=warnings,
    )
    if title and title != name:
        result["title"] = title
        for item in result["line_items"]:
            item["title"] = title
    if document_family.endswith("report"):
        result["doc_type"] = "report"
        for item in result["line_items"]:
            item["doc_type"] = "report"
    return result


def _parse_docx_material(index: int, item: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    name = str(item.get("name") or f"material_{index}.docx")
    raw = _material_bytes(item)
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    line_items: list[dict[str, Any]] = []
    for para_no, paragraph in enumerate(root.findall(".//w:body/w:p", WORD_NS), start=1):
        text = "".join(node.text for node in paragraph.findall(".//w:t", WORD_NS) if node.text).strip()
        if not text:
            continue
        paragraphs.append(text)
        line_items.append(
            {
                "text": text,
                "locator": {"paragraph": para_no, "source": "upload", "format": "docx"},
            }
        )
    return _build_result(
        index=index,
        name=name,
        scenario_id=scenario_id,
        source_type="uploaded_docx",
        parse_status="parsed_docx_text",
        text="\n".join(paragraphs),
        line_items=line_items,
    )


def _parse_xlsx_material(index: int, item: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    name = str(item.get("name") or f"material_{index}.xlsx")
    raw = _material_bytes(item)
    workbook = openpyxl.load_workbook(BytesIO(raw), data_only=True)
    rows: list[str] = []
    line_items: list[dict[str, Any]] = []
    for sheet in workbook.worksheets:
        for row_no, values in enumerate(sheet.iter_rows(values_only=True), start=1):
            normalized = [str(value).strip() for value in values if value not in (None, "") and str(value).strip()]
            if not normalized:
                continue
            text = " | ".join(normalized)
            rows.append(text)
            line_items.append(
                {
                    "text": text,
                    "locator": {"sheet": sheet.title, "row": row_no, "source": "upload", "format": "xlsx"},
                }
            )
    return _build_result(
        index=index,
        name=name,
        scenario_id=scenario_id,
        source_type="uploaded_xlsx",
        parse_status="parsed_xlsx_text",
        text="\n".join(rows),
        line_items=line_items,
    )


def _parse_error_material(index: int, item: dict[str, Any], scenario_id: str, exc: Exception) -> dict[str, Any]:
    name = str(item.get("name") or f"material_{index}")
    ext = _extension(name)
    return _build_result(
        index=index,
        name=name,
        scenario_id=scenario_id,
        source_type=f"uploaded_{ext}",
        parse_status="parse_error",
        text="",
        line_items=[],
        warnings=[f"{type(exc).__name__}: {exc}"],
    )


def _dispatch_parse(index: int, item: dict[str, Any], scenario_id: str, question_text: str | None = None) -> dict[str, Any]:
    name = str(item.get("name") or f"material_{index}")
    ext = _extension(name)
    if ext in TEXT_EXTENSIONS:
        return _parse_text_material(index, item, scenario_id)
    if ext == "pdf":
        return _parse_pdf_material(index, item, scenario_id, question_text=question_text)
    if ext == "docx":
        return _parse_docx_material(index, item, scenario_id)
    if ext == "xlsx":
        return _parse_xlsx_material(index, item, scenario_id)
    return _build_result(
        index=index,
        name=name,
        scenario_id=scenario_id,
        source_type="unsupported_upload",
        parse_status="unsupported_format",
        text="",
        line_items=[],
        warnings=[f"unsupported extension: {ext}"],
    )


def parse_uploaded_materials(materials: list[dict[str, Any]], scenario_id: str, question_text: str | None = None) -> dict[str, Any]:
    parsed_materials: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for index, item in enumerate(materials, start=1):
        name = str(item.get("name") or f"material_{index}")
        ext = _extension(name)
        try:
            parsed = _dispatch_parse(index, item, scenario_id, question_text=question_text)
        except Exception as exc:
            parsed = _parse_error_material(index, item, scenario_id, exc)
        if parsed["parse_status"] == "unsupported_format":
            unsupported.append({"name": name, "extension": ext})
        elif parsed["parse_status"] == "parse_error":
            warning = parsed["warnings"][0] if parsed.get("warnings") else "parse_error"
            unsupported.append({"name": name, "extension": ext, "error": warning})
        parsed_materials.append(parsed)

    return {
        "parsed_materials": parsed_materials,
        "unsupported_files": unsupported,
        "document_count": len(parsed_materials),
    }
