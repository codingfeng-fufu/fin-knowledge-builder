from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..catalog import RuleCatalog
from ..replay import load_trace, resolve_trace_path, summarize_trace
from ..runtime_core import Phase1Runtime
from ..schema import load_document_bundle, load_question


DEFAULT_RULES_PATH = "phase1_runtime/fixtures"
DEFAULT_QUESTION_PATH = "phase1_runtime/fixtures/question_private_fund_nav_warning.json"
DEFAULT_BUNDLE_PATH = "phase1_runtime/fixtures/document_bundle_private_fund_nav_warning.json"
DEFAULT_TRACE_DIR = "phase1_runtime/traces"
DEFAULT_RULE_PATTERN = "rule*.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the thicker Phase 1 direct-match runtime demo.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run direct match execution against a rule file or directory.")
    run_parser.add_argument("--rules-path", default=DEFAULT_RULES_PATH, help="Rule file or directory.")
    run_parser.add_argument("--rule-pattern", default=DEFAULT_RULE_PATTERN, help="Glob pattern when --rules-path is a directory.")
    run_parser.add_argument("--question", default=DEFAULT_QUESTION_PATH, help="Path to the sample question JSON file.")
    run_parser.add_argument("--bundle", default=DEFAULT_BUNDLE_PATH, help="Path to the sample facts/evidence JSON file.")
    run_parser.add_argument("--trace-dir", default=DEFAULT_TRACE_DIR, help="Directory where execution traces should be written.")
    run_parser.add_argument("--min-signal-hits", default=1, type=int, help="Minimum lexical signal hits required for direct match.")
    run_parser.add_argument("--retrieval-top-k", default=5, type=int, help="How many retrieval candidates to record in the trace.")

    replay_parser = subparsers.add_parser("replay", help="Summarize a saved trace.")
    replay_parser.add_argument("trace_path", nargs="?", help="Path to a trace JSON file. Defaults to the latest trace.")
    replay_parser.add_argument("--trace-dir", default=DEFAULT_TRACE_DIR, help="Directory to search when trace_path is omitted.")
    replay_parser.add_argument("--full", action="store_true", help="Print the full trace JSON instead of a summary.")

    catalog_parser = subparsers.add_parser("catalog", help="List rules from a file or directory.")
    catalog_parser.add_argument("--rules-path", default=DEFAULT_RULES_PATH, help="Rule file or directory.")
    catalog_parser.add_argument("--rule-pattern", default=DEFAULT_RULE_PATTERN, help="Glob pattern when --rules-path is a directory.")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    incoming = list(sys.argv[1:] if argv is None else argv)
    if not incoming or incoming[0] not in {"run", "replay", "catalog"}:
        incoming = ["run", *incoming]
    return parser.parse_args(incoming)


def handle_run(args: argparse.Namespace) -> dict[str, object]:
    catalog = RuleCatalog.from_path(args.rules_path, pattern=args.rule_pattern)
    question = load_question(args.question)
    facts, evidence_refs = load_document_bundle(args.bundle)

    runtime = Phase1Runtime(
        trace_dir=args.trace_dir,
        min_signal_hits=args.min_signal_hits,
        retrieval_top_k=args.retrieval_top_k,
    )
    result = runtime.run(question=question, rules=catalog.rules(), facts=facts, evidence_refs=evidence_refs)
    trace_summary = summarize_trace(load_trace(result.trace_path))

    return {
        "trace_id": result.trace_id,
        "trace_path": str(Path(result.trace_path).resolve()),
        "route_decision": result.route_decision,
        "status": result.status,
        "matched_rule_id": result.matched_rule_id,
        "failure_reason": result.failure_reason,
        "final_result": result.final_result,
        "catalog_size": len(catalog.entries),
        "trace_summary": trace_summary,
    }


def handle_replay(args: argparse.Namespace) -> dict[str, object]:
    trace_path = resolve_trace_path(args.trace_path, args.trace_dir)
    trace = load_trace(trace_path)
    if args.full:
        return trace
    summary = summarize_trace(trace)
    summary["trace_path"] = str(trace_path.resolve())
    return summary


def handle_catalog(args: argparse.Namespace) -> dict[str, object]:
    catalog = RuleCatalog.from_path(args.rules_path, pattern=args.rule_pattern)
    return {
        "rules_path": str(Path(args.rules_path).resolve()),
        "rule_count": len(catalog.entries),
        "rules": catalog.summaries(),
    }


def main() -> None:
    args = parse_args()
    if args.command == "run":
        payload = handle_run(args)
    elif args.command == "replay":
        payload = handle_replay(args)
    elif args.command == "catalog":
        payload = handle_catalog(args)
    else:
        raise ValueError(f"unsupported command {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
