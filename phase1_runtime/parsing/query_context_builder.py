from __future__ import annotations

import re
from typing import Any

from ..schema import InputField


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    tokens.extend(word.lower() for word in re.findall(r"[A-Za-z0-9]+", text))
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(cjk)
    for index in range(len(cjk) - 1):
        tokens.append(cjk[index] + cjk[index + 1])
    return tokens


def _query_mode(question_text: str) -> str:
    text = question_text.strip()
    if any(token in text for token in ("评级", "投资评级", "增持", "买入", "减持", "卖出", "中性")):
        return "rating"
    if any(token in text for token in ("目标价", "估值", "PB", "PE", "上涨空间")):
        return "target_price"
    if any(token in text for token in ("风险", "下行风险", "风险提示")):
        return "risk"
    return "general"


def _hint_terms(required_inputs: list[InputField]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for field in required_inputs:
        terms: set[str] = set()
        for hint in field.hints:
            hint_text = str(hint).strip()
            if not hint_text:
                continue
            terms.update(_tokenize(hint_text))
        mapping[field.key] = terms
    return mapping


def _chunk_terms(chunk: dict[str, Any]) -> set[str]:
    locator = chunk.get("locator", {})
    parts = [
        str(chunk.get("text", "")),
        str(locator.get("section", "")),
        str(locator.get("block_type", "")),
    ]
    terms: set[str] = set()
    for part in parts:
        terms.update(_tokenize(part))
    return terms


def _block_relevance(
    chunk: dict[str, Any],
    *,
    question_terms: set[str],
    all_hint_terms: set[str],
    query_mode: str,
) -> tuple[int, list[str]]:
    terms = _chunk_terms(chunk)
    query_overlap = sorted(question_terms & terms)
    hint_overlap = sorted(all_hint_terms & terms)
    score = len(query_overlap) * 3 + len(hint_overlap) * 4
    if score > 0 and chunk.get("chunk_type") in {"heading", "clause"}:
        score += 1
    text = str(chunk.get("text", "")).strip()
    locator = chunk.get("locator", {})
    section = str(locator.get("section") or "")
    if query_mode == "rating":
        if re.fullmatch(r"(增持|买入|中性|减持|卖出)（?(维持|上调|下调|首次覆盖|首次)?）?", text):
            score += 25
        if "投资评级" in section or "评级" in section:
            score += 10
    elif query_mode == "target_price":
        if "目标价" in text or re.search(r"\d+(?:\.\d+)?\s*元", text):
            score += 18
        if any(token in section for token in ("估值", "目标价")):
            score += 8
    elif query_mode == "risk":
        if "风险提示" in text or "下行风险" in text:
            score += 18
        if "风险" in section:
            score += 8
    return score, sorted(set(query_overlap + hint_overlap))


def _evidence_ref_from_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": chunk.get("doc_id"),
        "snippet_id": chunk.get("chunk_id"),
        "text": str(chunk.get("text", ""))[:240],
        "locator": dict(chunk.get("locator", {})),
    }


def build_query_context(
    *,
    question_text: str,
    document_chunks: list[dict[str, Any]],
    required_inputs: list[InputField],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    question_terms = set(_tokenize(question_text))
    query_mode = _query_mode(question_text)
    hint_term_map = _hint_terms(required_inputs)
    all_hint_terms = set().union(*hint_term_map.values()) if hint_term_map else set()

    scored_blocks: list[dict[str, Any]] = []
    score_by_chunk_id: dict[str, int] = {}
    for chunk in document_chunks:
        score, matched_terms = _block_relevance(
            chunk,
            question_terms=question_terms,
            all_hint_terms=all_hint_terms,
            query_mode=query_mode,
        )
        score_by_chunk_id[str(chunk.get("chunk_id"))] = score
        enriched = dict(chunk)
        enriched["relevance_score"] = score
        enriched["matched_terms"] = matched_terms
        scored_blocks.append(enriched)

    relevant_blocks = sorted(
        [item for item in scored_blocks if item["relevance_score"] > 0],
        key=lambda item: (item["relevance_score"], len(str(item.get("text", "")))),
        reverse=True,
    )[:8]
    if not relevant_blocks:
        relevant_blocks = scored_blocks[: min(5, len(scored_blocks))]

    evidence_units = [
        {
            **_evidence_ref_from_chunk(chunk),
            "chunk_type": chunk.get("chunk_type"),
            "relevance_score": chunk.get("relevance_score", 0),
        }
        for chunk in relevant_blocks
    ]

    fact_candidates: list[dict[str, Any]] = []
    context_gaps: list[str] = []
    for field in required_inputs:
        hints = hint_term_map.get(field.key, set())
        matched_chunks: list[dict[str, Any]] = []
        for chunk in scored_blocks:
            chunk_hint_overlap = hints & _chunk_terms(chunk)
            if chunk_hint_overlap:
                enriched = dict(chunk)
                enriched["field_matched_terms"] = sorted(chunk_hint_overlap)
                matched_chunks.append(enriched)
        matched_chunks = sorted(
            matched_chunks,
            key=lambda item: (
                len(item.get("field_matched_terms", [])) * 5 + score_by_chunk_id.get(str(item.get("chunk_id")), 0),
                len(str(item.get("text", ""))),
            ),
            reverse=True,
        )[:2]

        status = "grounded" if matched_chunks or not field.hints else "missing"
        if status == "missing":
            context_gaps.append(field.key)
        fact_candidates.append(
            {
                "fact_id": field.key,
                "fact_type": field.type,
                "status": status,
                "matched_terms": sorted({term for chunk in matched_chunks for term in chunk.get("field_matched_terms", [])}),
                "matched_block_ids": [chunk.get("chunk_id") for chunk in matched_chunks],
                "evidence_refs": [_evidence_ref_from_chunk(chunk) for chunk in matched_chunks],
            }
        )

    primary_document = documents[0] if documents else {}
    context_summary = "\n".join(
        str(chunk.get("text", "")).strip()
        for chunk in relevant_blocks[:4]
        if str(chunk.get("text", "")).strip()
    )

    return {
        "document_profile": {
            "document_count": len(documents),
            "document_ids": [item.get("doc_id") for item in documents],
            "document_types": [item.get("doc_type") for item in documents],
            "primary_title": primary_document.get("title"),
            "primary_doc_type": primary_document.get("doc_type"),
        },
        "query_profile": {
            "question_text": question_text,
            "question_terms": sorted(question_terms),
            "query_mode": query_mode,
            "required_input_keys": [field.key for field in required_inputs],
        },
        "relevant_blocks": relevant_blocks,
        "evidence_units": evidence_units,
        "fact_candidates": fact_candidates,
        "context_summary": context_summary,
        "context_gaps": context_gaps,
    }
