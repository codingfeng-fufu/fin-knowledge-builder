from __future__ import annotations

from dataclasses import dataclass

from .hybrid_retrieval_types import RetrievalQuery


@dataclass(slots=True)
class QueryRewrite:
    rewrite_id: str
    text: str
    strategy: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rewrite_id": self.rewrite_id,
            "text": self.text,
            "strategy": self.strategy,
        }


def _unique_parts(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in parts:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def rewrite_retrieval_query(query: RetrievalQuery, *, max_rewrites: int = 4) -> list[QueryRewrite]:
    candidate_payloads = [
        (
            "original_question",
            query.question_text,
        ),
        (
            "semantic_context",
            query.semantic_text,
        ),
        (
            "typed_intent",
            " | ".join(
                _unique_parts(
                    [
                        query.question_text,
                        "question_types: " + ", ".join(query.question_types) if query.question_types else "",
                        "intents: " + ", ".join(query.intents) if query.intents else "",
                        "document_types: " + ", ".join(query.document_types) if query.document_types else "",
                    ]
                )
            ),
        ),
        (
            "facts_and_evidence",
            " | ".join(
                _unique_parts(
                    [
                        query.question_text,
                        "fact_keys: " + ", ".join(sorted(query.fact_keys)) if query.fact_keys else "",
                        "evidence_terms: " + ", ".join(sorted(list(query.evidence_terms))[:18]) if query.evidence_terms else "",
                    ]
                )
            ),
        ),
        (
            "input_focused",
            " | ".join(
                _unique_parts(
                    [
                        query.question_text,
                        "extracted_inputs: "
                        + ", ".join(f"{key}={value}" for key, value in sorted(query.extracted_inputs.items()))
                        if query.extracted_inputs
                        else "",
                    ]
                )
            ),
        ),
    ]

    rewrites: list[QueryRewrite] = []
    seen_texts: set[str] = set()
    for index, (strategy, text) in enumerate(candidate_payloads):
        normalized = text.strip()
        if not normalized or normalized in seen_texts:
            continue
        seen_texts.add(normalized)
        rewrites.append(
            QueryRewrite(
                rewrite_id=f"rewrite_{index:02d}",
                text=normalized,
                strategy=strategy,
            )
        )
        if len(rewrites) >= max_rewrites:
            break
    return rewrites
