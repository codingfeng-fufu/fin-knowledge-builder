from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

import fitz


_PLUGIN_SCRIPT = Path(__file__).resolve().parents[2] / "plugins" / "claude-style-pdf-reader" / "scripts" / "read_pdf.py"
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"
_DEFAULT_MODEL = "kimi-k2.5"
_DEFAULT_QUERY_PAGE_BUDGET = 4
_DEFAULT_NO_QUERY_PAGE_BUDGET = 3
_DISCLAIMER_MARKERS = (
    "免责声明",
    "重要声明",
    "评级说明",
    "法律声明",
    "声明",
)

_PDF_UNDERSTANDING_PROMPT = """Read this PDF page as a document-understanding system, not as a plain text extractor.

Return strict JSON only. Do not wrap it in markdown fences.

Use exactly this schema:
{
  "title": string | null,
  "document_family": string | null,
  "blocks": [
    {
      "block_type": "title" | "heading" | "paragraph" | "table_row" | "disclaimer" | "header" | "footer",
      "section": string | null,
      "page": number | null,
      "text": string
    }
  ],
  "semantic_signals": [
    {
      "signal_type": string,
      "value": string | null,
      "page": number | null
    }
  ]
}

Rules:
- Focus on readable document understanding.
- Preserve section boundaries and reading order as well as possible.
- Include only meaningful blocks; do not flood the result with isolated characters.
- Put repeated page furniture, disclaimers, and contact info into header/footer/disclaimer blocks when present.
- Use null only when a field is genuinely unavailable.
- If the page is poorly extracted, still return your best structured understanding from the visible content.
"""


def _build_pdf_understanding_prompt(query_text: str | None = None) -> str:
    query = (query_text or "").strip()
    if not query:
        return _PDF_UNDERSTANDING_PROMPT
    return (
        f"{_PDF_UNDERSTANDING_PROMPT}\n\n"
        "Current user query:\n"
        f"{query}\n\n"
        "Extra rules for this query-aware read:\n"
        "- Prioritize blocks that are directly relevant to the current user query.\n"
        "- When multiple blocks are available, keep the blocks most useful for answering the query.\n"
        "- Prefer evidence-like text over generic boilerplate.\n"
        "- Keep enough surrounding context so downstream retrieval and answering can still reason correctly.\n"
    )


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    tokens.extend(word.lower() for word in re.findall(r"[A-Za-z0-9]{2,}", text))
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    for index in range(len(cjk) - 1):
        tokens.append(cjk[index] + cjk[index + 1])
    for index in range(len(cjk) - 2):
        tokens.append(cjk[index] + cjk[index + 1] + cjk[index + 2])
    return tokens


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start:end + 1])
        raise


def _normalize_json_like(value: Any) -> Any:
    current = value
    for _ in range(3):
        if isinstance(current, str):
            candidate = current.strip()
            if not candidate:
                return current
            try:
                current = _extract_json_object(candidate)
                continue
            except Exception:
                try:
                    current = json.loads(candidate)
                    continue
                except Exception:
                    return value
        break
    return current


def _load_runtime_config() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _normalize_block_type(raw: Any) -> str:
    value = str(raw or "paragraph").strip().lower()
    allowed = {"title", "heading", "paragraph", "table_row", "disclaimer", "header", "footer"}
    return value if value in allowed else "paragraph"


def _normalize_page(raw: Any, fallback_page: int) -> int:
    try:
        page = int(raw)
    except (TypeError, ValueError):
        return fallback_page
    return page if page > 0 else fallback_page


def _page_budget(page_count: int, query_text: str | None = None) -> int:
    raw = os.environ.get("KIMI_PDF_PAGE_BUDGET")
    if raw:
        try:
            budget = int(raw)
        except ValueError:
            budget = 0
        if budget > 0:
            return max(1, min(page_count, budget))
    default_budget = _DEFAULT_QUERY_PAGE_BUDGET if (query_text or "").strip() else _DEFAULT_NO_QUERY_PAGE_BUDGET
    return max(1, min(page_count, default_budget))


def _query_term_weights(page_texts: list[str], query_terms: set[str]) -> dict[str, float]:
    if not query_terms:
        return {}
    page_term_sets = [set(_tokenize(text)) for text in page_texts]
    page_count = max(1, len(page_term_sets))
    weights: dict[str, float] = {}
    for term in query_terms:
        document_frequency = sum(1 for term_set in page_term_sets if term in term_set)
        weights[term] = 1.0 + max(0.0, (page_count - document_frequency) / page_count)
    return weights


def _query_aspect_terms(query_text: str | None) -> set[str]:
    query = (query_text or "").strip()
    aspects: set[str] = set()
    if any(token in query for token in ["评级", "投资评级", "增持", "买入", "卖出", "中性"]):
        aspects.update({"评级", "投资评级", "增持", "买入", "卖出", "中性", "维持", "上调", "下调"})
    if any(token in query for token in ["目标价", "估值", "PB", "PE", "上涨空间"]):
        aspects.update({"目标价", "估值", "PB", "PE", "上涨空间", "股价空间"})
    if any(token in query for token in ["风险", "下行风险", "风险提示"]):
        aspects.update({"风险", "下行风险", "风险提示"})
    return aspects


def _score_page_text(page_text: str, query_terms: set[str], query_weights: dict[str, float], aspect_terms: set[str]) -> tuple[int, list[str]]:
    page_terms = set(_tokenize(page_text))
    overlap = sorted(query_terms & page_terms)
    aspect_overlap = sorted(term for term in aspect_terms if term and term in page_text)
    score = int(round(sum(query_weights.get(term, 1.0) for term in overlap) * 5))
    score += len(aspect_overlap) * 12
    if aspect_terms and not aspect_overlap:
        score -= 8
    if any(marker in page_text for marker in _DISCLAIMER_MARKERS):
        score -= 20
    score = max(0, score)
    return score, overlap


def _select_pages_from_texts(page_texts: list[str], query_text: str | None = None) -> tuple[list[int], dict[str, Any]]:
    page_count = len(page_texts)
    if page_count == 0:
        return [], {"mode": "empty_pdf", "page_budget": 0, "scored_pages": []}

    budget = _page_budget(page_count, query_text=query_text)
    query_terms = set(_tokenize(query_text or ""))
    query_weights = _query_term_weights(page_texts, query_terms)
    aspect_terms = _query_aspect_terms(query_text)
    scored_pages: list[dict[str, Any]] = []
    for index, page_text in enumerate(page_texts, start=1):
        score, overlap = _score_page_text(page_text, query_terms, query_weights, aspect_terms)
        scored_pages.append(
            {
                "page": index,
                "score": score,
                "matched_terms": overlap,
                "matched_aspect_terms": sorted(term for term in aspect_terms if term and term in page_text),
                "has_text": bool(page_text.strip()),
            }
        )

    if not query_terms:
        selected = list(range(1, budget + 1))
        return selected, {
            "mode": "sequential_no_query",
            "page_budget": budget,
            "scored_pages": scored_pages,
        }

    selected: list[int] = [1]
    positive_pages = sorted(
        [item for item in scored_pages if item["score"] > 0 and item["page"] != 1],
        key=lambda item: (item["score"], item["page"]),
        reverse=True,
    )

    for item in positive_pages:
        if len(selected) >= budget:
            break
        selected.append(int(item["page"]))

    if len(selected) < budget:
        for item in list(selected):
            for neighbor in (item - 1, item + 1):
                if 1 <= neighbor <= page_count and neighbor not in selected:
                    selected.append(neighbor)
                    if len(selected) >= budget:
                        break
            if len(selected) >= budget:
                break

    if len(selected) < budget:
        for page_no in range(1, page_count + 1):
            if page_no not in selected:
                selected.append(page_no)
            if len(selected) >= budget:
                break

    selected = sorted(selected[:budget])
    mode = "query_ranked" if any(item["score"] > 0 for item in scored_pages) else "fallback_first_pages"
    return selected, {
        "mode": mode,
        "page_budget": budget,
        "scored_pages": scored_pages,
    }


def _invoke_plugin_page(pdf_path: Path, page_no: int, timeout_seconds: int, query_text: str | None = None) -> dict[str, Any]:
    cfg = _load_runtime_config()
    api_key = cfg.get("moonshot_api_key") or os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")
    base_url = cfg.get("moonshot_base_url") or os.environ.get("MOONSHOT_BASE_URL") or os.environ.get("KIMI_BASE_URL")
    model = os.environ.get("MOONSHOT_PDF_MODEL") or os.environ.get("KIMI_PDF_MODEL") or _DEFAULT_MODEL

    cmd = [
        "python3",
        str(_PLUGIN_SCRIPT),
        str(pdf_path),
        "--pages",
        f"{page_no}-{page_no}",
        "--output-mode",
        "plugin-json",
        "--full",
        "--model",
        model,
        "--no-default-prompt",
        "--prompt",
        _build_pdf_understanding_prompt(query_text),
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    if base_url:
        cmd.extend(["--base-url", str(base_url)])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PDF plugin page call failed")
    payload = json.loads(result.stdout)
    if not payload.get("ok"):
        raise RuntimeError(f"PDF plugin returned non-ok payload: {payload}")
    return payload


def _normalize_page_understanding(payload: dict[str, Any], page_no: int) -> dict[str, Any]:
    answer = ((payload.get("analysis") or {}).get("answer")) or ""
    try:
        parsed = _normalize_json_like(answer)
        if not isinstance(parsed, dict):
            raise ValueError("page answer did not normalize to an object")
    except Exception:
        recovered = _recover_jsonish_page(answer, page_no)
        parsed = {
            "title": recovered["title"],
            "document_family": recovered["document_family"],
            "blocks": recovered["blocks"],
            "semantic_signals": recovered["semantic_signals"],
        }

    blocks: list[dict[str, Any]] = []
    for item in parsed.get("blocks") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        blocks.append(
            {
                "block_type": _normalize_block_type(item.get("block_type")),
                "section": None if item.get("section") in (None, "") else str(item.get("section")),
                "page": _normalize_page(item.get("page"), page_no),
                "text": text,
            }
        )

    semantic_signals: list[dict[str, Any]] = []
    for item in parsed.get("semantic_signals") or []:
        if not isinstance(item, dict):
            continue
        signal_type = str(item.get("signal_type", "")).strip()
        if not signal_type:
            continue
        semantic_signals.append(
            {
                "signal_type": signal_type,
                "value": None if item.get("value") in (None, "") else str(item.get("value")),
                "page": _normalize_page(item.get("page"), page_no),
            }
        )

    return {
        "title": None if parsed.get("title") in (None, "") else str(parsed.get("title")),
        "document_family": None if parsed.get("document_family") in (None, "") else str(parsed.get("document_family")),
        "blocks": blocks,
        "semantic_signals": semantic_signals,
        "raw_plugin_payload": payload,
    }


def _merge_page_results(page_results: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    title = None
    document_family = None
    blocks: list[dict[str, Any]] = []
    semantic_signals: list[dict[str, Any]] = []
    raw_payloads: list[dict[str, Any]] = []
    block_counter = 1

    for page_no, understood in sorted(page_results, key=lambda item: item[0]):
        raw_payloads.append(understood.get("raw_plugin_payload") or {})
        if title is None and understood.get("title"):
            title = understood["title"]
        if document_family is None and understood.get("document_family"):
            document_family = understood["document_family"]

        for block in understood.get("blocks") or []:
            normalized = dict(block)
            normalized["block_id"] = f"block_{block_counter:03d}"
            blocks.append(normalized)
            block_counter += 1

        semantic_signals.extend(list(understood.get("semantic_signals") or []))

    return {
        "title": title,
        "document_family": document_family,
        "blocks": blocks,
        "semantic_signals": semantic_signals,
        "raw_plugin_payload": raw_payloads,
    }


def _recover_jsonish_page(answer: str, page_no: int) -> dict[str, Any]:
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    title = None
    document_family = None
    blocks: list[dict[str, Any]] = []
    semantic_signals: list[dict[str, Any]] = []

    current: dict[str, Any] | None = None
    for line in lines:
        title_match = re.match(r'"title"\s*:\s*"(.*)"[,]?$', line)
        if title_match and title is None:
            title = title_match.group(1)
            continue
        family_match = re.match(r'"document_family"\s*:\s*"(.*)"[,]?$', line)
        if family_match and document_family is None:
            document_family = family_match.group(1)
            continue
        block_type_match = re.match(r'"block_type"\s*:\s*"(.*)"[,]?$', line)
        if block_type_match:
            if current and current.get("text"):
                blocks.append(current)
            current = {
                "block_type": _normalize_block_type(block_type_match.group(1)),
                "section": None,
                "page": page_no,
                "text": "",
            }
            continue
        section_match = re.match(r'"section"\s*:\s*(null|"(.*)")[,]?$', line)
        if section_match and current is not None:
            current["section"] = None if section_match.group(1) == "null" else section_match.group(2)
            continue
        page_match = re.match(r'"page"\s*:\s*(null|\d+)[,]?$', line)
        if page_match and current is not None:
            current["page"] = page_no if page_match.group(1) == "null" else int(page_match.group(1))
            continue
        text_match = re.match(r'"text"\s*:\s*"(.*)"[,]?$', line)
        if text_match and current is not None:
            current["text"] = text_match.group(1)
            continue

    if current and current.get("text"):
        blocks.append(current)

    if not blocks:
        blocks = [
            {
                "block_type": "paragraph",
                "section": None,
                "page": page_no,
                "text": line,
            }
            for line in lines
            if not line.startswith(('"block_type"', '"section"', '"page"', '"text"', '{', '}', '],', '],', '[', ']'))
        ]

    return {
        "title": title,
        "document_family": document_family,
        "blocks": blocks,
        "semantic_signals": semantic_signals,
    }


def understand_pdf_bytes(raw: bytes, query_text: str | None = None) -> dict[str, Any]:
    if not _PLUGIN_SCRIPT.exists():
        raise FileNotFoundError(f"PDF plugin script not found: {_PLUGIN_SCRIPT}")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        with fitz.open(str(tmp_path)) as document:
            page_count = document.page_count
            page_texts = []
            for page in document:
                try:
                    page_texts.append(page.get_text("text") or "")
                except Exception:
                    page_texts.append("")

        selected_pages, page_selection = _select_pages_from_texts(page_texts, query_text=query_text)

        timeout_seconds = int(os.environ.get("KIMI_PDF_PAGE_TIMEOUT_SECONDS", "300"))
        concurrency = min(len(selected_pages), int(os.environ.get("KIMI_PDF_PAGE_CONCURRENCY", "8")))
        page_results: list[tuple[int, dict[str, Any]]] = []

        def _run(page_no: int) -> tuple[int, dict[str, Any]]:
            payload = _invoke_plugin_page(tmp_path, page_no, timeout_seconds, query_text=query_text)
            return page_no, _normalize_page_understanding(payload, page_no)

        with ThreadPoolExecutor(max_workers=max(concurrency, 1)) as executor:
            futures = [executor.submit(_run, page_no) for page_no in selected_pages]
            for future in as_completed(futures):
                page_results.append(future.result())

        merged = _merge_page_results(page_results)
        merged["page_selection"] = {
            **page_selection,
            "selected_pages": selected_pages,
            "page_count": page_count,
        }
        return merged
    finally:
        tmp_path.unlink(missing_ok=True)
