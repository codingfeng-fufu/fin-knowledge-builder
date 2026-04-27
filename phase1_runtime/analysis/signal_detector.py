from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..parsing.document_chunk import DocumentChunk
    from ..schema import InputField


def detect_input_signals(
    chunks: list[DocumentChunk],
    required_inputs: list[InputField],
) -> dict[str, bool]:
    """
    For each required input field, check if any of its hint keywords appear
    in the document chunks. Returns {fact_key: signal_present}.

    A signal is considered present if at least one hint keyword appears
    in any chunk's text (case-insensitive for ASCII, exact match for CJK).
    """
    if not chunks:
        return {field.key: False for field in required_inputs}

    full_text = " ".join(chunk.text for chunk in chunks).lower()

    result: dict[str, bool] = {}
    for field in required_inputs:
        if not field.hints:
            # No hints defined — assume signal present (don't block execution)
            result[field.key] = True
            continue
        present = any(hint.lower() in full_text for hint in field.hints)
        result[field.key] = present
    return result


def build_signal_fact_sheet(
    signal_results: dict[str, bool],
    required_inputs: list[InputField],
) -> list[dict[str, Any]]:
    """
    Convert signal detection results into a fact_sheet compatible structure.
    signal_present  → status = "grounded"  (routing will attempt execution)
    signal_absent   → status = "missing"   (routing returns needs_more_context)
    """
    fact_sheet: list[dict[str, Any]] = []
    for field in required_inputs:
        present = signal_results.get(field.key, True)
        fact_sheet.append({
            "fact_id": field.key,
            "fact_type": field.type,
            "value": None,
            "status": "grounded" if present else "missing",
            "source": "signal_detection",
            "evidence_refs": [],
        })
    return fact_sheet
