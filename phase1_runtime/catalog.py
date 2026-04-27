from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import Rule, load_rule


@dataclass(slots=True)
class CatalogEntry:
    path: Path
    rule: Rule

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "rule_id": self.rule.rule_id,
            "name": self.rule.name,
            "status": self.rule.status,
            "version": self.rule.version,
            "question_types": self.rule.trigger.question_types,
            "intents": self.rule.trigger.intents,
            "document_types": self.rule.applicability.document_types,
        }


class RuleCatalog:
    def __init__(self, entries: list[CatalogEntry]) -> None:
        self.entries = entries

    @classmethod
    def from_path(cls, path: str | Path, pattern: str = "rule*.json") -> "RuleCatalog":
        source = Path(path)
        if source.is_file():
            return cls([CatalogEntry(path=source, rule=load_rule(source))])
        if source.is_dir():
            entries = [CatalogEntry(path=item, rule=load_rule(item)) for item in sorted(source.glob(pattern))]
            return cls(entries)
        raise FileNotFoundError(f"rule path not found: {source}")

    def rules(self) -> list[Rule]:
        return [entry.rule for entry in self.entries]

    def summaries(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self.entries]
