from __future__ import annotations

from typing import Iterable

from .hybrid_retrieval_types import IndexedAssetRecord, tokenize_text
from ..schema import Rule


def _output_keys(rule: Rule) -> set[str]:
    properties = rule.outputs.answer_schema.get("properties", {})
    if isinstance(properties, dict) and properties:
        return set(properties.keys())
    return {field.key for field in rule.steps[-1].io.outputs}


def _support_terms(rule: Rule) -> set[str]:
    terms: set[str] = set()
    terms.update(tokenize_text(rule.name))
    terms.update(tokenize_text(rule.rule_family))
    terms.update(tokenize_text(rule.applicability.scope))
    terms.update(tokenize_text(rule.applicability.non_scope))
    for field in rule.inputs.required:
        terms.update(tokenize_text(field.key))
        terms.update(tokenize_text(field.description))
    for field in rule.inputs.optional:
        terms.update(tokenize_text(field.key))
        terms.update(tokenize_text(field.description))
    for key in _output_keys(rule):
        terms.update(tokenize_text(key))
    return terms


def _semantic_text(rule: Rule) -> str:
    parts = [
        rule.name,
        rule.rule_family,
        " ".join(rule.trigger.query_signals),
        rule.applicability.scope,
    ]
    for field in rule.inputs.required:
        parts.append(field.key)
        parts.append(field.description)
    for field in rule.inputs.optional:
        parts.append(field.key)
        parts.append(field.description)
    for key in _output_keys(rule):
        parts.append(key)
    return "\n".join(part for part in parts if part)


def _semantic_focus_text(rule: Rule) -> str:
    parts = [
        rule.applicability.scope,
        " ".join(rule.trigger.query_signals),
    ]
    return "\n".join(part for part in parts if part)


def index_rule(rule: Rule) -> IndexedAssetRecord:
    semantic_text = _semantic_text(rule)
    semantic_focus_text = _semantic_focus_text(rule)
    return IndexedAssetRecord(
        asset_type="rule",
        asset_id=rule.rule_id,
        rule_id=rule.rule_id,
        rule_kind=rule.rule_kind,
        rule_family=rule.rule_family,
        status=rule.status,
        question_types=set(rule.trigger.question_types),
        intents=set(rule.trigger.intents),
        document_types=set(rule.applicability.document_types),
        query_signals={signal.lower() for signal in rule.trigger.query_signals},
        support_terms=_support_terms(rule),
        semantic_text=semantic_text,
        semantic_terms=tokenize_text(semantic_text),
        semantic_focus_text=semantic_focus_text,
        semantic_focus_terms=tokenize_text(semantic_focus_text),
        negative_terms=tokenize_text(rule.applicability.non_scope),
        required_input_keys={field.key for field in rule.inputs.required},
        optional_input_keys={field.key for field in rule.inputs.optional},
        output_keys=_output_keys(rule),
        metadata={
            "step_count": len(rule.steps),
            "validator_count": len(rule.validators),
        },
        rule=rule,
    )


def build_rule_asset_index(rules: Iterable[Rule]) -> list[IndexedAssetRecord]:
    return [index_rule(rule) for rule in rules]
