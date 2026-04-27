from __future__ import annotations

from typing import Any

from ..schema import EvidenceRef, QuestionStruct
from .hybrid_retrieval_types import RetrievalQuery, normalize_value_terms, tokenize_text


def build_retrieval_query(
    question: QuestionStruct,
    facts: dict[str, Any] | None = None,
    evidence_refs: list[EvidenceRef | dict[str, Any]] | None = None,
    retrieval_fact_keys: set[str] | list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RetrievalQuery:
    fact_values = {} if facts is None else dict(facts)
    signal_fact_keys = {str(key) for key in (retrieval_fact_keys or []) if str(key)}
    evidence_terms: set[str] = set()
    for item in evidence_refs or []:
        if isinstance(item, dict):
            evidence_terms.update(tokenize_text(str(item.get("text", ""))))
        else:
            evidence_terms.update(tokenize_text(item.text))

    fact_terms: set[str] = set()
    for key, value in fact_values.items():
        fact_terms.update(tokenize_text(str(key)))
        fact_terms.update(normalize_value_terms(value))

    extracted_terms: set[str] = set()
    for key, value in question.extracted_inputs.items():
        extracted_terms.update(tokenize_text(str(key)))
        extracted_terms.update(normalize_value_terms(value))

    question_terms = tokenize_text(question.question_text)
    lexical_terms = set(question_terms) | set(extracted_terms) | set(fact_terms) | set(evidence_terms)
    fact_keys = set(fact_values.keys()) | set(question.extracted_inputs.keys()) | signal_fact_keys
    semantic_parts = [
        question.question_text,
        " ".join(sorted(str(key) for key in fact_keys)),
        " ".join(sorted(str(value) for value in fact_values.values())),
        " ".join(sorted(str(key) for key in question.extracted_inputs.keys())),
    ]
    for item in evidence_refs or []:
        if isinstance(item, dict):
            semantic_parts.append(str(item.get("text", "")))
        else:
            semantic_parts.append(item.text)
    semantic_text = "\n".join(part for part in semantic_parts if part)
    return RetrievalQuery(
        question_text=question.question_text,
        question_types=list(question.question_types),
        intents=list(question.intents),
        document_types=list(question.document_types),
        extracted_inputs=dict(question.extracted_inputs),
        fact_values=fact_values,
        fact_keys=fact_keys,
        question_terms=question_terms,
        evidence_terms=evidence_terms,
        lexical_terms=lexical_terms,
        semantic_text=semantic_text,
        semantic_terms=tokenize_text(semantic_text),
        question_semantic_text=question.question_text,
        question_semantic_terms=tokenize_text(question.question_text),
        metadata={} if metadata is None else dict(metadata),
    )
