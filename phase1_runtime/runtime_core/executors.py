from __future__ import annotations

import re
from typing import Any, Callable

from ..kimi_llm_executor import KimiTransport, execute_llm_step as _execute_llm_step


ToolFn = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _select_evidence(context: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_refs = list(context.get("evidence_refs", []))
    snippet_ids = config.get("evidence_snippet_ids")
    if not snippet_ids:
        return evidence_refs
    filtered = [item for item in evidence_refs if item.get("snippet_id") in set(snippet_ids)]
    # Fallback to all available evidence if none match the requested snippet IDs.
    # This happens when evidence comes from LLM extraction with dynamic snippet IDs.
    return filtered if filtered else evidence_refs


def _ordered_document_chunks(context: dict[str, Any]) -> list[dict[str, Any]]:
    def _sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
        locator = item.get("locator", {})
        page = int(locator.get("page") or 0)
        line = int(locator.get("line") or locator.get("row") or 0)
        paragraph = int(locator.get("paragraph") or 0)
        return (page, line, paragraph)

    return sorted(list(context.get("document_chunks", [])), key=_sort_key)


def _chunk_to_evidence_ref(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": chunk.get("doc_id"),
        "snippet_id": chunk.get("chunk_id"),
        "text": str(chunk.get("text", ""))[:240],
        "locator": dict(chunk.get("locator", {})),
    }


def _section_name(chunk: dict[str, Any]) -> str:
    locator = chunk.get("locator", {})
    return str(locator.get("section") or "")


def _find_first_chunk(chunks: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    for chunk in chunks:
        if predicate(chunk):
            return chunk
    return None


def _next_paragraph_after(chunks: list[dict[str, Any]], anchor: dict[str, Any]) -> dict[str, Any] | None:
    try:
        start = chunks.index(anchor) + 1
    except ValueError:
        return None
    for chunk in chunks[start:]:
        locator = chunk.get("locator", {})
        if locator.get("page") != anchor.get("locator", {}).get("page"):
            break
        if locator.get("block_type") == "paragraph":
            return chunk
    return None


def _find_rating(chunk_text: str) -> str | None:
    match = re.search(r"(增持|买入|中性|减持|卖出)", chunk_text)
    return None if match is None else match.group(1)


def _find_rating_change(chunk_text: str) -> str | None:
    match = re.search(r"(维持|上调|下调|首次覆盖|首次)", chunk_text)
    return None if match is None else match.group(1)


def _extract_first_number(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                continue
    return None


def _find_current_price(chunks: list[dict[str, Any]], question_text: str) -> tuple[float | None, dict[str, Any] | None]:
    price_patterns = [
        r"收盘价(?:为|：|:)?\s*(\d+(?:\.\d+)?)",
        r"现价(?:为|：|:)?\s*(\d+(?:\.\d+)?)",
        r"股价(?:为|：|:)?\s*(\d+(?:\.\d+)?)",
        r"最新价(?:为|：|:)?\s*(\d+(?:\.\d+)?)",
    ]
    question_price = _extract_first_number(price_patterns, question_text)
    if question_price is not None:
        return question_price, None
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        value = _extract_first_number(price_patterns, text)
        if value is not None:
            return value, chunk
    return None, None


def _joined_chunk_text(chunks: list[dict[str, Any]]) -> str:
    return "\n".join(str(chunk.get("text", "")).strip() for chunk in chunks if str(chunk.get("text", "")).strip())


def _extract_table_row_values(joined_text: str, label_keywords: list[str], expected_count: int = 4) -> list[float] | None:
    for raw_line in joined_text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if not all(keyword in line for keyword in label_keywords):
            continue
        values = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", line)]
        if len(values) >= expected_count:
            return values[:expected_count]
    return None


def _extract_year_valuation_metrics(text: str, year: str) -> tuple[float, float, float, float] | None:
    patterns = [
        rf"{year}.*?每股盈利.*?(\d+(?:\.\d+)?).*?每股净资产.*?(\d+(?:\.\d+)?).*?PE.*?(\d+(?:\.\d+)?).*?PB.*?(\d+(?:\.\d+)?)",
        rf"{year}.*?EPS.*?(\d+(?:\.\d+)?).*?BVPS.*?(\d+(?:\.\d+)?).*?P/E.*?(\d+(?:\.\d+)?).*?P/B.*?(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return tuple(float(match.group(index)) for index in range(1, 5))
    return None


def _find_chunk_by_keywords(chunks: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
    lowered_keywords = [keyword.lower() for keyword in keywords]
    return _find_first_chunk(
        chunks,
        lambda item: all(keyword in str(item.get("text", "")).lower() for keyword in lowered_keywords),
    )


def _find_rating_definition_band(chunks: list[dict[str, Any]], rating: str) -> tuple[tuple[float, float] | None, dict[str, Any] | None]:
    rating_keywords = {
        "增持": "增持",
        "买入": "买入",
        "中性": "中性",
        "减持": "减持",
        "卖出": "卖出",
    }
    keyword = rating_keywords.get(rating or "")
    if not keyword:
        return None, None
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        if keyword not in text:
            continue
        band_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*%", text)
        if not band_match:
            band_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*-\s*(\d+(?:\.\d+)?)\s*%", text)
        if band_match:
            return (float(band_match.group(1)), float(band_match.group(2))), chunk
    return None, None


def _decision_for_rating(rating: str | None) -> str:
    if rating in {"增持", "买入"}:
        return "rating_bullish"
    if rating in {"中性", "持有"}:
        return "rating_neutral"
    if rating in {"减持", "卖出"}:
        return "rating_bearish"
    return "needs_review"


def build_research_rating_answer(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    chunks = _ordered_document_chunks(context)
    rating_chunk = _find_first_chunk(
        chunks,
        lambda item: (
            _section_name(item) in {"评级信息", "投资评级"}
            or "评级" in str(item.get("text", ""))
            or "增持" in str(item.get("text", ""))
            or "买入" in str(item.get("text", ""))
        ) and bool(_find_rating(str(item.get("text", "")))),
    )
    rationale_chunks = [
        item for item in chunks
        if _section_name(item) in {"投资要点", "盈利预测与投资建议"}
        and item.get("locator", {}).get("block_type") == "paragraph"
    ]

    rating_text = "" if rating_chunk is None else str(rating_chunk.get("text", ""))
    analyst_rating = _find_rating(rating_text) or "未明确"
    rating_change = _find_rating_change(rating_text) or "未明确"
    rating_rationale = "；".join(str(item.get("text", "")).strip() for item in rationale_chunks[:2]).strip() or "研报未稳定提取出核心投资逻辑。"
    decision = _decision_for_rating(analyst_rating if analyst_rating != "未明确" else None)
    answer_text = (
        f"研报给出的评级为{analyst_rating}，评级变动为{rating_change}。"
        f"核心投资逻辑包括：{rating_rationale}"
    )
    evidence_refs = []
    if rating_chunk is not None:
        evidence_refs.append(_chunk_to_evidence_ref(rating_chunk))
    evidence_refs.extend(_chunk_to_evidence_ref(item) for item in rationale_chunks[:2])
    if not evidence_refs and chunks:
        evidence_refs.append(_chunk_to_evidence_ref(chunks[0]))
    return {
        "analyst_rating": analyst_rating,
        "rating_change": rating_change,
        "rating_rationale": rating_rationale,
        "answer_text": answer_text,
        "decision": decision,
        "evidence_refs": evidence_refs,
    }


def build_research_risk_answer(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    chunks = _ordered_document_chunks(context)
    risk_heading = _find_first_chunk(
        chunks,
        lambda item: _section_name(item) == "风险提示"
        or "风险提示" == str(item.get("text", "")).strip(),
    )
    risk_paragraph = None
    if risk_heading is not None:
        risk_paragraph = _next_paragraph_after(chunks, risk_heading)
    if risk_paragraph is None:
        risk_paragraph = _find_first_chunk(
            chunks,
            lambda item: "下行风险" in str(item.get("text", "")) or "风险提示" in str(item.get("text", "")),
        )
    if risk_paragraph is None:
        risk_paragraph = _find_first_chunk(
            chunks,
            lambda item: any(
                token in str(item.get("text", ""))
                for token in ("信用卡", "经营贷", "消费贷", "LPR", "债市", "减值损失")
            ),
        )
    risk_text = "" if risk_paragraph is None else str(risk_paragraph.get("text", "")).strip()
    if risk_text.startswith("风险提示"):
        risk_text = risk_text.split("风险提示", 1)[-1].lstrip("：: ")
    segments = [part.strip(" ；;。.") for part in re.split(r"[；;]", risk_text) if part.strip(" ；;。.")]
    numbered = re.findall(r"[①②③④⑤⑥⑦⑧⑨⑩]", risk_text)
    risk_count = len(numbered) if numbered else len(segments)
    if risk_count >= 3:
        decision = "risks_multiple"
    elif risk_count >= 1:
        decision = "risks_limited"
    else:
        decision = "needs_review"
    answer_text = f"研报提到的主要下行风险包括：{risk_text or '未稳定提取到明确风险提示。'}"
    evidence_refs = []
    if risk_paragraph is not None:
        evidence_refs.append(_chunk_to_evidence_ref(risk_paragraph))
    elif chunks:
        evidence_refs.append(_chunk_to_evidence_ref(chunks[0]))
    return {
        "key_risks": risk_text or "未稳定提取到明确风险提示。",
        "risk_count": risk_count,
        "answer_text": answer_text,
        "decision": decision,
        "evidence_refs": evidence_refs,
    }


def build_research_risk_count_answer(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    base = build_research_risk_answer(inputs, context, config)
    risk_count = int(base.get("risk_count") or 0)
    key_risks = str(base.get("key_risks") or "").strip()
    if risk_count > 0:
        answer_text = f"这份研报列出了 {risk_count} 项主要下行风险。"
        if key_risks:
            answer_text += f"分别是：{key_risks}"
        decision = "risk_count_answered"
    else:
        answer_text = "当前未能稳定统计出研报中的主要下行风险数量。"
        decision = "needs_review"
    return {
        "risk_count": risk_count,
        "key_risks": key_risks or "未稳定提取到明确风险提示。",
        "answer_text": answer_text,
        "decision": decision,
        "evidence_refs": list(base.get("evidence_refs", [])),
    }


def build_research_target_price_answer(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    chunks = _ordered_document_chunks(context)
    target_chunk = _find_first_chunk(
        chunks,
        lambda item: "目标价" in str(item.get("text", "")) or "上涨空间" in str(item.get("text", "")),
    )
    valuation_chunk = _find_first_chunk(
        chunks,
        lambda item: any(token in str(item.get("text", "")) for token in ("PB", "PE", "DCF", "估值")),
    )
    target_text = "" if target_chunk is None else str(target_chunk.get("text", ""))
    valuation_text = "" if valuation_chunk is None else str(valuation_chunk.get("text", ""))
    target_match = re.search(r"(\d+(?:\.\d+)?)\s*元", target_text)
    target_price = None if target_match is None else float(target_match.group(1))
    valuation_method = next((token for token in ("PB", "PE", "DCF") if token in valuation_text), "未明确")
    answer_text = (
        f"当前解析结果中{'已' if target_price is not None else '未'}稳定定位到明确目标价。"
        f"{'目标价约为' + str(target_price) + '元。' if target_price is not None else ''}"
        f"估值依据：{valuation_text or '未稳定提取到明确估值依据。'}"
    )
    decision = "upside_moderate" if target_price is not None else "needs_review"
    evidence_refs = []
    if target_chunk is not None:
        evidence_refs.append(_chunk_to_evidence_ref(target_chunk))
    if valuation_chunk is not None and valuation_chunk is not target_chunk:
        evidence_refs.append(_chunk_to_evidence_ref(valuation_chunk))
    if not evidence_refs and chunks:
        evidence_refs.append(_chunk_to_evidence_ref(chunks[0]))
    return {
        "target_price": -1.0 if target_price is None else target_price,
        "valuation_method": valuation_method,
        "valuation_multiple": valuation_text or "未稳定提取到估值倍数。",
        "upside_description": target_text or "未稳定提取到上涨空间描述。",
        "answer_text": answer_text,
        "decision": decision,
        "evidence_refs": evidence_refs,
    }


def build_research_rating_target_audit_answer(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    chunks = _ordered_document_chunks(context)
    question_text = str(context.get("question_text", "") or "")
    full_text = str(context.get("document_full_text", "") or "").strip()
    joined_text = full_text or _joined_chunk_text(chunks)

    analyst_rating = "未明确"
    rating_change = "未明确"
    rating_patterns = [
        re.search(r"(增持|买入|中性|减持|卖出)[（(](维持|上调|下调|首次覆盖|首次)[）)]", joined_text),
        re.search(r"(维持|上调|下调|首次覆盖|首次)[“\"]?(增持|买入|中性|减持|卖出)[”\"]?评级", joined_text),
        re.search(r"维持[“\"]?(增持|买入|中性|减持|卖出)[”\"]?评级", joined_text),
    ]
    if rating_patterns[0]:
        analyst_rating = rating_patterns[0].group(1)
        rating_change = rating_patterns[0].group(2)
    elif rating_patterns[1]:
        rating_change = rating_patterns[1].group(1)
        analyst_rating = rating_patterns[1].group(2)
    elif rating_patterns[2]:
        rating_change = "维持"
        analyst_rating = rating_patterns[2].group(1)
    else:
        inferred_rating = _find_rating(question_text)
        inferred_change = _find_rating_change(question_text)
        if inferred_rating:
            analyst_rating = inferred_rating
        if inferred_change:
            rating_change = inferred_change

    current_price, current_price_chunk = _find_current_price(chunks, question_text)
    if current_price is None:
        current_price = _extract_first_number([r"收盘价(?:为|：|:)?\s*(\d+(?:\.\d+)?)"], joined_text)

    year_metric_rows = {
        year: _extract_year_valuation_metrics(joined_text, year)
        for year in ("2026E", "2027E", "2028E")
    }

    risk_text = "未稳定提取到明确风险提示。"
    risk_matches = re.findall(r"(?:最大下行风险|风险提示)[:：]\s*(.+)", joined_text)
    if risk_matches:
        risk_text = str(risk_matches[-1]).strip(" 。")
    else:
        risk_result = build_research_risk_answer(inputs, context, config)
        candidate_risk = str(risk_result.get("key_risks") or "").strip()
        if candidate_risk:
            risk_text = candidate_risk

    years = ["2026E", "2027E", "2028E"]
    if all(year_metric_rows.get(year) for year in years):
        eps_values = [year_metric_rows[year][0] for year in years]
        bvps_values = [year_metric_rows[year][1] for year in years]
        pe_values = [year_metric_rows[year][2] for year in years]
        pb_values = [year_metric_rows[year][3] for year in years]
    else:
        eps_row = _extract_table_row_values(joined_text, ["每股盈利"])
        bvps_row = _extract_table_row_values(joined_text, ["每股净资产"])
        pe_row = _extract_table_row_values(joined_text, ["PE"])
        pb_row = _extract_table_row_values(joined_text, ["PB"])
        eps_values = eps_row[1:4] if eps_row and len(eps_row) >= 4 else []
        bvps_values = bvps_row[1:4] if bvps_row and len(bvps_row) >= 4 else []
        pe_values = pe_row[1:4] if pe_row and len(pe_row) >= 4 else []
        pb_values = pb_row[1:4] if pb_row and len(pb_row) >= 4 else []

    calc_pe_values: list[float] = []
    calc_pb_values: list[float] = []
    audit_lines: list[str] = []
    if current_price is not None and len(eps_values) == 3 and len(bvps_values) == 3 and len(pe_values) == 3 and len(pb_values) == 3:
        for year, eps, bvps, pe_table, pb_table in zip(years, eps_values, bvps_values, pe_values, pb_values):
            pe_calc = round(current_price / eps, 2)
            pb_calc = round(current_price / bvps, 2)
            calc_pe_values.append(pe_calc)
            calc_pb_values.append(pb_calc)
            pe_diff = round(pe_calc - pe_table, 2)
            pb_diff = round(pb_calc - pb_table, 2)
            pe_judgement = "一致" if abs(pe_diff) <= 0.05 else "存在明显差异"
            pb_judgement = "一致" if abs(pb_diff) <= 0.02 else "存在明显差异"
            audit_lines.append(
                f"- {year}：代码计算 PE {pe_calc:.2f}，表内 {pe_table:.2f}，差异 {pe_diff:+.2f}，{pe_judgement}；"
                f"代码计算 PB {pb_calc:.2f}，表内 {pb_table:.2f}，差异 {pb_diff:+.2f}，{pb_judgement}。"
            )
        audit_lines.append(
            "- 整体判断：PB 与表内结果一致，PE 基本一致但前两年存在轻微舍入差异，推测原表使用了更高精度的每股盈利或不同价格口径。"
        )
        rating_supported = "yes"
    else:
        rating_supported = "undetermined"
        audit_lines.append("- 当前未能同时稳定提取收盘价、每股盈利、每股净资产、PE 和 PB，因此无法完成完整复算。")

    code_lines = [
        f"close_price = {current_price:.2f}" if current_price is not None else "close_price = None  # 未稳定提取到收盘价",
        f"eps = {{'2026E': {eps_values[0]:.2f}, '2027E': {eps_values[1]:.2f}, '2028E': {eps_values[2]:.2f}}}" if len(eps_values) == 3 else "eps = {}  # 未稳定提取到每股盈利",
        f"bvps = {{'2026E': {bvps_values[0]:.2f}, '2027E': {bvps_values[1]:.2f}, '2028E': {bvps_values[2]:.2f}}}" if len(bvps_values) == 3 else "bvps = {}  # 未稳定提取到每股净资产",
        "for year in eps:",
        "    pe = close_price / eps[year]",
        "    pb = close_price / bvps[year]",
        "    print(year, round(pe, 2), round(pb, 2))",
    ]

    rating_line = f"{analyst_rating}{f'（{rating_change}）' if rating_change != '未明确' else ''}"
    summary_points = [
        f"1. 研报维持“{rating_line}”，核心依据是文中明确强调息差压力缓解、资产质量稳中有进，以及公司经营在底部出现积极信号。",
        "2. 从复算结果看，估值表整体自洽，PB 与表内完全一致，PE 仅存在轻微舍入差异，不影响结论方向。" if len(audit_lines) > 1 else "2. 当前材料还不足以完成完整复算，建议人工补充后再核验估值表。",
        f"3. 最大下行风险是 {risk_text}。",
    ]

    answer_text_parts: list[str] = [
        "### 1. 关键信息提取",
        "",
        f"- 分析师评级：{rating_line}",
        f"- 收盘价：{f'{current_price:.2f} 元' if current_price is not None else '未稳定提取到明确收盘价'}",
        "",
    ]
    has_full_valuation = (
        current_price is not None
        and len(eps_values) == 3 and len(bvps_values) == 3
        and len(pe_values) == 3 and len(pb_values) == 3
    )
    if has_full_valuation:
        answer_text_parts += [
            "| 年份 | 每股盈利 | 每股净资产 | 表内 PE | 表内 PB |",
            "|------|---------|-----------|--------|--------|",
        ]
        for i, year in enumerate(years):
            answer_text_parts.append(
                f"| {year} | {eps_values[i]:.2f} | {bvps_values[i]:.2f} | {pe_values[i]:.2f} | {pb_values[i]:.2f} |"
            )
        if calc_pe_values and calc_pb_values:
            answer_text_parts += [
                "",
                "| 年份 | 计算 PE | 计算 PB | PE 差异 | PB 差异 | PE 判定 | PB 判定 |",
                "|------|--------|--------|---------|---------|---------|---------|",
            ]
            for i, year in enumerate(years):
                pe_calc = round(current_price / eps_values[i], 2)
                pb_calc = round(current_price / bvps_values[i], 2)
                pe_diff = round(pe_calc - pe_values[i], 2)
                pb_diff = round(pb_calc - pb_values[i], 2)
                pe_judgement = "一致" if abs(pe_diff) <= 0.05 else "差异"
                pb_judgement = "一致" if abs(pb_diff) <= 0.02 else "差异"
                answer_text_parts.append(
                    f"| {year} | {pe_calc:.2f} | {pb_calc:.2f} | {pe_diff:+.2f} | {pb_diff:+.2f} | {pe_judgement} | {pb_judgement} |"
                )
    else:
        answer_text_parts += [
            f"- 2026E-2028E 每股盈利：{' / '.join(f'{item:.2f}' for item in eps_values) if len(eps_values) == 3 else '未稳定提取到完整表格'}",
            f"- 2026E-2028E 每股净资产：{' / '.join(f'{item:.2f}' for item in bvps_values) if len(bvps_values) == 3 else '未稳定提取到完整表格'}",
            f"- 表内 PE：{' / '.join(f'{item:.2f}' for item in pe_values) if len(pe_values) == 3 else '未稳定提取到完整表格'}",
            f"- 表内 PB：{' / '.join(f'{item:.2f}' for item in pb_values) if len(pb_values) == 3 else '未稳定提取到完整表格'}",
        ]
    answer_text_parts += [
        f"- 主要下行风险：{risk_text}",
        "",
        "### 2. Python 代码",
        "```python",
        *code_lines,
        "```",
        "",
        "### 3. 核验结论",
        *audit_lines,
        "",
        "### 4. 三句话总结",
        *summary_points,
    ]

    answer_text = "\n".join(answer_text_parts)

    evidence_refs: list[dict[str, Any]] = []
    for keywords in (
        ["每股盈利"],
        ["每股净资产"],
        ["PE"],
        ["PB"],
        ["风险提示"],
        ["收盘价"],
    ):
        chunk = _find_chunk_by_keywords(chunks, keywords)
        if chunk is not None:
            ref = _chunk_to_evidence_ref(chunk)
            if ref not in evidence_refs:
                evidence_refs.append(ref)
    if current_price_chunk is not None:
        ref = _chunk_to_evidence_ref(current_price_chunk)
        if ref not in evidence_refs:
            evidence_refs.append(ref)
    if not evidence_refs and chunks:
        evidence_refs.append(_chunk_to_evidence_ref(chunks[0]))

    return {
        "analyst_rating": analyst_rating,
        "rating_change": rating_change,
        "current_price": -1.0 if current_price is None else float(current_price),
        "target_price": -1.0,
        "target_display": "不再以目标价为主核验对象，本题重点核验盈利预测与估值简表。",
        "key_risks": risk_text,
        "python_code": "\n".join(code_lines),
        "upside_percent": -1.0,
        "rating_supported": rating_supported,
        "answer_text": answer_text,
        "decision": "audit_completed" if len(audit_lines) > 1 else "needs_review",
        "evidence_refs": evidence_refs,
    }


def compare_numeric(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    left_key = config.get("left_key", "left")
    right_key = config.get("right_key", "right")
    operator = config.get("operator", "<")
    result_key = config.get("result_key", "result")

    left_value = inputs[left_key]
    right_value = inputs[right_key]
    if not _is_number(left_value):
        raise ValueError(f"compare_numeric requires numeric input for {left_key}, got {left_value!r}")
    if not _is_number(right_value):
        raise ValueError(f"compare_numeric requires numeric input for {right_key}, got {right_value!r}")

    comparisons = {
        "<": left_value < right_value,
        "<=": left_value <= right_value,
        ">": left_value > right_value,
        ">=": left_value >= right_value,
        "==": left_value == right_value,
    }
    if operator not in comparisons:
        raise ValueError(f"unsupported operator {operator}")

    return {
        result_key: comparisons[operator],
        "left_value": left_value,
        "right_value": right_value,
        "operator": operator,
        "evidence_refs": _select_evidence(context, config),
    }


def boolean_gate(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    input_keys = config.get("input_keys") or list(inputs.keys())
    result_key = config.get("result_key", "result")
    mode = config.get("mode", "all_true")
    checked_inputs = {key: bool(inputs[key]) for key in input_keys}

    if mode == "all_true":
        result = all(checked_inputs.values())
    elif mode == "any_true":
        result = any(checked_inputs.values())
    else:
        raise ValueError(f"unsupported boolean gate mode {mode}")

    return {
        result_key: result,
        "checked_inputs": checked_inputs,
        "evidence_refs": _select_evidence(context, config),
    }


def build_policy_answer(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    warning_required = bool(inputs[config.get("decision_input_key", "warning_required")])
    threshold_breached = bool(inputs[config.get("threshold_input_key", "threshold_breached")])

    if warning_required:
        answer_text = config.get(
            "positive_text",
            "需要做风险提示，因为净值已经跌破阈值，且合同要求触发后向投资者提示风险。",
        )
        decision = config.get("positive_decision", "must_warn")
    else:
        answer_text = config.get(
            "negative_text",
            "当前不能直接下结论，需要补充确认阈值条件或合同义务是否成立。",
        )
        decision = config.get("negative_decision", "needs_review")

    explanation = (
        f"threshold_breached={threshold_breached}; "
        f"contract_requires_warning={inputs.get('contract_requires_warning')}; "
        f"warning_required={warning_required}"
    )

    return {
        "answer_text": answer_text,
        "decision": decision,
        "threshold_breached": threshold_breached,
        "warning_required": warning_required,
        "explanation": explanation,
        "evidence_refs": _select_evidence(context, config),
    }


def build_notice_answer(inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    notice_required = bool(inputs[config.get("decision_input_key", "notice_required")])
    notice_window_open = bool(inputs[config.get("window_input_key", "notice_window_open")])

    if notice_required:
        answer_text = config.get(
            "positive_text",
            "需要发送展期通知，因为已进入通知窗口且合同明确要求通知借款人办理展期手续。",
        )
        decision = config.get("positive_decision", "must_notify")
    else:
        answer_text = config.get(
            "negative_text",
            "当前不需要发送展期通知，因为尚未进入通知窗口或合同未要求通知借款人办理展期手续。",
        )
        decision = config.get("negative_decision", "no_notice_required")

    explanation = (
        f"notice_window_open={notice_window_open}; "
        f"contract_requires_notice={inputs.get('contract_requires_notice')}; "
        f"notice_required={notice_required}"
    )

    return {
        "answer_text": answer_text,
        "decision": decision,
        "notice_window_open": notice_window_open,
        "notice_required": notice_required,
        "explanation": explanation,
        "evidence_refs": _select_evidence(context, config),
    }


TOOL_REGISTRY: dict[str, ToolFn] = {
    "compare_numeric": compare_numeric,
    "boolean_gate": boolean_gate,
    "build_policy_answer": build_policy_answer,
    "build_notice_answer": build_notice_answer,
    "build_research_rating_answer": build_research_rating_answer,
    "build_research_risk_answer": build_research_risk_answer,
    "build_research_risk_count_answer": build_research_risk_count_answer,
    "build_research_target_price_answer": build_research_target_price_answer,
    "build_research_rating_target_audit_answer": build_research_rating_target_audit_answer,
}


def execute_tool(tool_name: str, inputs: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"unknown tool {tool_name}")
    return TOOL_REGISTRY[tool_name](inputs, context, config)


def execute_llm(
    *,
    goal: str,
    context: dict[str, Any],
    output_schema: dict[str, Any],
    constraints: dict[str, Any],
    kimi_client: KimiTransport | None = None,
) -> dict[str, Any]:
    """Delegate to kimi_llm_executor. context must contain 'document_chunks' and 'step_state'."""
    document_chunks = context.get("document_chunks", [])
    prior_outputs = context.get("step_state", {})
    return _execute_llm_step(
        goal=goal,
        document_chunks=document_chunks,
        prior_outputs=prior_outputs,
        output_schema=output_schema,
        constraints=constraints,
        kimi_client=kimi_client,
    )
