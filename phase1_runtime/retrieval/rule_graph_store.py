from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import argparse
from typing import Any, Iterable

from ..catalog import RuleCatalog
from ..schema import Rule
from .asset_index import build_rule_asset_index
from .rule_graph import RuleCommunity, RuleGraphIndex, build_rule_graph_index
from .rule_graph_rag import RuleRagPassage, build_rule_graph_rag_catalog


DEFAULT_RULE_GRAPH_STATE_DIR = Path("phase1_runtime/state/rule_graph")
DEFAULT_RULE_GRAPH_RULES_PATH = Path("phase1_runtime/fixtures")
DEFAULT_RULE_GRAPH_RULE_PATTERN = "rule*.json"
RULE_GRAPH_ARTIFACT_SCHEMA_VERSION = "v3_leiden_hierarchical_reports"


def _normalize_rules(rules: Iterable[Rule]) -> list[Rule]:
    return sorted(list(rules), key=lambda item: item.rule_id)


def fingerprint_rules(rules: Iterable[Rule]) -> str:
    normalized = [rule.to_dict() for rule in _normalize_rules(rules)]
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _artifact_root(output_dir: str | Path, fingerprint: str) -> Path:
    return Path(output_dir) / fingerprint


def _manifest_path(output_dir: str | Path, fingerprint: str) -> Path:
    return _artifact_root(output_dir, fingerprint) / "manifest.json"


def _communities_path(output_dir: str | Path, fingerprint: str) -> Path:
    return _artifact_root(output_dir, fingerprint) / "communities.json"


def _rag_catalog_path(output_dir: str | Path, fingerprint: str) -> Path:
    return _artifact_root(output_dir, fingerprint) / "rag_catalog.json"


def _latest_manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "latest.json"


def materialize_rule_graph_artifacts(
    rules: Iterable[Rule],
    *,
    output_dir: str | Path = DEFAULT_RULE_GRAPH_STATE_DIR,
) -> dict[str, Any]:
    normalized_rules = _normalize_rules(rules)
    fingerprint = fingerprint_rules(normalized_rules)
    graph_index = build_rule_graph_index(normalized_rules)
    rag_catalog = build_rule_graph_rag_catalog(graph_index)

    root = _artifact_root(output_dir, fingerprint)
    root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": RULE_GRAPH_ARTIFACT_SCHEMA_VERSION,
        "fingerprint": fingerprint,
        "generated_at": datetime.now(UTC).isoformat(),
        "rule_count": len(normalized_rules),
        "community_count": len(graph_index.communities),
        "rag_passage_count": len(rag_catalog),
        "graph_backend": graph_index.metadata.get("graph_backend"),
    }
    _manifest_path(output_dir, fingerprint).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _communities_path(output_dir, fingerprint).write_text(
        json.dumps(
            {
                "community_by_rule_id": dict(graph_index.community_by_rule_id),
                "communities": [community.to_dict() for community in graph_index.communities],
                "metadata": dict(graph_index.metadata),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _rag_catalog_path(output_dir, fingerprint).write_text(
        json.dumps(
            {
                "passages": [passage.to_dict() for passage in rag_catalog],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _latest_manifest_path(output_dir).write_text(
        json.dumps({"fingerprint": fingerprint, "root": str(root), "generated_at": manifest["generated_at"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "artifact_root": str(root.resolve()),
        "fingerprint": fingerprint,
        "manifest": manifest,
    }


def load_persisted_rule_graph_artifacts(
    rules: Iterable[Rule],
    *,
    output_dir: str | Path = DEFAULT_RULE_GRAPH_STATE_DIR,
) -> tuple[RuleGraphIndex, list[RuleRagPassage], dict[str, Any]] | None:
    normalized_rules = _normalize_rules(rules)
    fingerprint = fingerprint_rules(normalized_rules)
    manifest_path = _manifest_path(output_dir, fingerprint)
    communities_path = _communities_path(output_dir, fingerprint)
    rag_catalog_path = _rag_catalog_path(output_dir, fingerprint)
    if not manifest_path.exists() or not communities_path.exists() or not rag_catalog_path.exists():
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("fingerprint")) != fingerprint:
        return None
    if str(manifest.get("schema_version")) != RULE_GRAPH_ARTIFACT_SCHEMA_VERSION:
        return None

    communities_payload = json.loads(communities_path.read_text(encoding="utf-8"))
    rag_payload = json.loads(rag_catalog_path.read_text(encoding="utf-8"))

    graph_index = RuleGraphIndex(
        records=build_rule_asset_index(normalized_rules),
        communities=[RuleCommunity.from_dict(item) for item in communities_payload.get("communities", [])],
        community_by_rule_id={str(key): str(value) for key, value in communities_payload.get("community_by_rule_id", {}).items()},
        metadata=dict(communities_payload.get("metadata", {})) | {"loaded_from_cache": True},
    )
    rag_catalog = [RuleRagPassage.from_dict(item) for item in rag_payload.get("passages", [])]
    return graph_index, rag_catalog, {
        "fingerprint": fingerprint,
        "artifact_root": str(_artifact_root(output_dir, fingerprint).resolve()),
        "cache_hit": True,
        "manifest": manifest,
    }


def load_or_build_rule_graph_artifacts(
    rules: Iterable[Rule],
    *,
    output_dir: str | Path = DEFAULT_RULE_GRAPH_STATE_DIR,
) -> tuple[RuleGraphIndex, list[RuleRagPassage], dict[str, Any]]:
    cached = load_persisted_rule_graph_artifacts(rules, output_dir=output_dir)
    if cached is not None:
        return cached

    materialized = materialize_rule_graph_artifacts(rules, output_dir=output_dir)
    loaded = load_persisted_rule_graph_artifacts(rules, output_dir=output_dir)
    if loaded is None:
        raise RuntimeError("rule graph artifacts were materialized but could not be reloaded")
    graph_index, rag_catalog, metadata = loaded
    metadata["cache_hit"] = False
    metadata["manifest"] = materialized["manifest"]
    return graph_index, rag_catalog, metadata


def resolve_rule_graph_output_dir(
    *,
    db_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    if db_path is None:
        return DEFAULT_RULE_GRAPH_STATE_DIR
    return Path(db_path).resolve().parent / "rule_graph"


def collect_active_rules_for_rule_graph(
    *,
    db_path: str | Path | None = None,
    rules_path: str | Path = DEFAULT_RULE_GRAPH_RULES_PATH,
    pattern: str = DEFAULT_RULE_GRAPH_RULE_PATTERN,
    include_published: bool = True,
) -> list[Rule]:
    catalog = RuleCatalog.from_path(rules_path, pattern=pattern)
    merged = {rule.rule_id: rule for rule in catalog.rules()}
    if include_published:
        if db_path is None:
            from ..factory.rule_factory_retrieval import list_published_rules

            published_rules = list_published_rules()
        else:
            from ..factory.rule_factory_retrieval import list_published_rules

            published_rules = list_published_rules(db_path=db_path)
        for rule in published_rules:
            merged[rule.rule_id] = rule
    return sorted(merged.values(), key=lambda item: item.rule_id)


def rebuild_active_rule_graph_artifacts(
    *,
    db_path: str | Path | None = None,
    rules_path: str | Path = DEFAULT_RULE_GRAPH_RULES_PATH,
    pattern: str = DEFAULT_RULE_GRAPH_RULE_PATTERN,
    include_published: bool = True,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_output_dir = resolve_rule_graph_output_dir(db_path=db_path, output_dir=output_dir)
    rules = collect_active_rules_for_rule_graph(
        db_path=db_path,
        rules_path=rules_path,
        pattern=pattern,
        include_published=include_published,
    )
    payload = materialize_rule_graph_artifacts(rules, output_dir=resolved_output_dir)
    payload["output_dir"] = str(resolved_output_dir.resolve())
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize persisted rule-graph and graph-RAG artifacts.")
    parser.add_argument("--rules-path", default="phase1_runtime/fixtures")
    parser.add_argument("--pattern", default="rule*.json")
    parser.add_argument("--output-dir", default=str(DEFAULT_RULE_GRAPH_STATE_DIR))
    parser.add_argument("--include-published", action="store_true")
    args = parser.parse_args(argv)

    payload = rebuild_active_rule_graph_artifacts(
        db_path=None,
        rules_path=args.rules_path,
        pattern=args.pattern,
        include_published=args.include_published,
        output_dir=args.output_dir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
