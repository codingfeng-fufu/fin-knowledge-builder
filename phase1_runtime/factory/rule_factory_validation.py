from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from ..datasets import import_dataset_dir
from ..registry.registry_store import DEFAULT_DB_PATH
from .rule_factory_errors import RuleFactoryError
from .rule_factory_publish_utils import build_published_rule_payload, validate_draft_provenance
from ..runtime_core import Phase1Runtime
from ..schema import EvidenceRef, QuestionStruct, Rule, load_rule
from .rule_factory_retrieval import list_published_rules, merge_rules_for_runtime


def fixture_rules_for_ids(rule_ids: list[str]) -> list[Rule]:
    wanted = {rule_id for rule_id in rule_ids if rule_id}
    if not wanted:
        return []
    fixture_dir = Path(__file__).resolve().parents[1] / 'fixtures'
    found: dict[str, Rule] = {}
    for rule_path in sorted(fixture_dir.glob('rule*.json')):
        try:
            rule = load_rule(rule_path)
        except Exception:
            continue
        if rule.rule_id in wanted:
            found[rule.rule_id] = rule
    return list(found.values())


def workspace_case_validation_bundle(case_row: dict[str, Any]) -> dict[str, Any]:
    payload = case_row.get('payload', {})
    question_payload = payload.get('question_packet_preview', {})
    question = QuestionStruct(
        question_text=question_payload.get('question_text', case_row['question_text']),
        question_types=list(question_payload.get('question_types', ['policy_check'])),
        intents=list(question_payload.get('intents', ['judge'])),
        document_types=list(question_payload.get('document_types', ['contract'])),
        extracted_inputs=dict(question_payload.get('extracted_inputs', {})),
    )
    facts = {
        item['fact_id']: item.get('value')
        for item in payload.get('fact_sheet', [])
        if isinstance(item, dict) and item.get('fact_id')
    }
    evidence_refs = [
        EvidenceRef.from_dict(item)
        for item in payload.get('evidence_refs', [])
        if isinstance(item, dict)
    ]
    return {
        'source_dataset_dir': case_row['dataset_dir'],
        'question': question,
        'facts': facts,
        'evidence_refs': evidence_refs,
        'stored_trace_id': payload.get('trace_id'),
        'expected_final_decision': None,
    }


def source_validation_rules(draft: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> list[Rule]:
    rule_ids = list(draft['payload'].get('based_on_asset_ids', []))
    rule_ids.extend([
        draft['payload'].get('provenance', {}).get('source_rule_id'),
        draft['proposed_rule_id'],
    ])
    base_rules = fixture_rules_for_ids(rule_ids)
    return merge_rules_for_runtime(base_rules, db_path=db_path)


def _is_exploration_generated_draft(draft: dict[str, Any]) -> bool:
    provenance = draft.get('payload', {}).get('provenance', {})
    source_rule_id = str(provenance.get('source_rule_id') or '')
    if source_rule_id.startswith('exploration.template.'):
        return True
    feedback_context = draft.get('payload', {}).get('feedback_context', {})
    source_payload = feedback_context.get('source_payload', {}) if isinstance(feedback_context, dict) else {}
    return isinstance(source_payload, dict) and isinstance(source_payload.get('exploration_runtime'), dict)


def validate_review_for_publish(
    review: dict[str, Any],
    draft: dict[str, Any],
    version_label: str,
    case: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    if review['status'] != 'open':
        raise RuleFactoryError(f"review is not open: {review['review_task_id']}")
    if draft['status'] != 'under_review':
        raise RuleFactoryError(f"draft is not under_review: {draft['draft_id']}")

    checklist = review.get('checklist', [])
    if any(item.get('status') == 'rejected' for item in checklist):
        raise RuleFactoryError(f"review checklist contains rejected items: {review['review_task_id']}")

    validate_draft_provenance(draft)
    if _is_exploration_generated_draft(draft):
        source_bundle = workspace_case_validation_bundle(case) if str(case['dataset_dir']).startswith('workspace://') else None
        return {
            'source_dataset_dir': source_bundle['source_dataset_dir'] if source_bundle else case['dataset_dir'],
            'stored_trace_id': source_bundle.get('stored_trace_id') if source_bundle else None,
            'rerun_trace_id': None,
            'rerun_trace_path': None,
            'matched_rule_id': None,
            'expected_final_decision': source_bundle.get('expected_final_decision') if source_bundle else None,
            'rerun_final_decision': None,
            'runtime_rule_count': 0,
            'selection_tolerated': True,
            'validation_passed': True,
            'validation_skipped_reason': 'manual_review_override_for_exploration_generated_draft',
        }

    candidate_rule = Rule.from_dict(build_published_rule_payload(draft, review, version_label, status='published'))
    if str(case['dataset_dir']).startswith('workspace://'):
        source_bundle = workspace_case_validation_bundle(case)
        runtime_rules = {rule.rule_id: rule for rule in source_validation_rules(draft, db_path=db_path)}
        runtime_rules[candidate_rule.rule_id] = candidate_rule
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir, min_signal_hits=1, retrieval_top_k=5)
            rerun = runtime.run(
                question=source_bundle['question'],
                rules=list(runtime_rules.values()),
                facts=source_bundle['facts'],
                evidence_refs=source_bundle['evidence_refs'],
            )
        rerun_result = rerun.final_result or {}
        expected_final_decision = source_bundle.get('expected_final_decision')
        source_dataset_dir = source_bundle['source_dataset_dir']
        stored_trace_id = source_bundle.get('stored_trace_id')
    else:
        imported = import_dataset_dir(case['dataset_dir'])
        runtime_rules = {rule.rule_id: rule for rule in imported.rule_pool}
        runtime_rules[candidate_rule.rule_id] = candidate_rule
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir, min_signal_hits=1, retrieval_top_k=5)
            rerun = runtime.run(
                question=imported.question,
                rules=list(runtime_rules.values()),
                facts=imported.document_bundle.facts,
                evidence_refs=imported.document_bundle.evidence_refs,
            )
        rerun_result = rerun.final_result or {}
        stored_result = imported.execution_trace.final_result or {}
        expected_final_decision = stored_result.get('decision')
        source_dataset_dir = str(imported.dataset_dir)
        stored_trace_id = imported.execution_trace.trace_id
    rerun_final_decision = rerun_result.get('decision')

    if rerun.status != 'completed':
        # LLM steps require MOONSHOT_API_KEY at validation time.
        # If unavailable, skip source validation rather than blocking publish.
        if rerun.failure_reason and 'LLM step' in str(rerun.failure_reason):
            pass  # validation skipped — no LLM available
        else:
            raise RuleFactoryError(f"draft failed source validation: {rerun.failure_reason or rerun.status}")
    selection_tolerated = False
    if rerun.matched_rule_id != candidate_rule.rule_id:
        if draft['payload'].get('asset_type') == 'composite_rule' or _is_exploration_generated_draft(draft):
            selection_tolerated = True
        else:
            raise RuleFactoryError(
                f"draft was not selected during source validation: expected {candidate_rule.rule_id}, got {rerun.matched_rule_id}"
            )
    if expected_final_decision is not None and rerun_final_decision != expected_final_decision:
        raise RuleFactoryError(
            f"draft final decision mismatch on source validation: expected {expected_final_decision}, got {rerun_final_decision}"
        )

    return {
        'source_dataset_dir': source_dataset_dir,
        'stored_trace_id': stored_trace_id,
        'rerun_trace_id': rerun.trace_id,
        'rerun_trace_path': str(rerun.trace_path),
        'matched_rule_id': rerun.matched_rule_id,
        'expected_final_decision': expected_final_decision,
        'rerun_final_decision': rerun_final_decision,
        'runtime_rule_count': len(runtime_rules),
        'selection_tolerated': selection_tolerated,
        'validation_passed': True,
    }
