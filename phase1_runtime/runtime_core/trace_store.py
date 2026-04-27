from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TraceStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, trace_id: str, trace: dict[str, Any]) -> Path:
        path = self.base_dir / f"{trace_id}.json"
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
