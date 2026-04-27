from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .super_agent import ToolDefinition


DEFAULT_READ_LINE_LIMIT = 200
MAX_READ_LINE_LIMIT = 400


def _truncate(text: str, max_chars: int = 12_000) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n...[truncated {len(text) - max_chars} chars]"


def _split_lines(content: str) -> list[str]:
    return content.splitlines()


def _normalize_rel_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return "."
    return normalized.lstrip("./") or "."


@dataclass(slots=True)
class WorkspaceToolContext:
    workspace_root: Path

    def resolve(self, raw_path: str) -> Path:
        target = (self.workspace_root / raw_path).resolve()
        root = self.workspace_root.resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes workspace: {raw_path}") from exc
        return target

    def iter_files(self) -> list[Path]:
        return [path for path in self.workspace_root.rglob("*") if path.is_file()]


def _format_chunked_read_result(
    *,
    path: str,
    content: str,
    offset: int,
    limit: int,
) -> str:
    lines = _split_lines(content)
    total_lines = len(lines)
    if total_lines == 0:
        return f"[path] {path}\n[lines] 0-0 of 0"
    if offset > total_lines:
        return f"Read failed: {path} has {total_lines} lines, so offset {offset} is out of range."
    start_index = offset - 1
    selected = lines[start_index : start_index + limit]
    end_line = start_index + len(selected)
    header = f"[path] {path}\n[lines] {offset}-{end_line} of {total_lines}"
    return _truncate(f"{header}\n\n" + "\n".join(selected))


def _read_file_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        relative_path = str(input_data["path"])
        file_path = context.resolve(relative_path)
        content = file_path.read_text(encoding="utf-8")
        lines = _split_lines(content)
        if not lines:
            return f"[path] {relative_path}\n[lines] 0-0 of 0"
        head = input_data.get("head")
        tail = input_data.get("tail")
        offset = int(input_data.get("offset") or 1)
        limit = int(input_data.get("limit") or DEFAULT_READ_LINE_LIMIT)
        if isinstance(head, int) and head > 0:
            return _format_chunked_read_result(
                path=relative_path,
                content=content,
                offset=1,
                limit=min(head, MAX_READ_LINE_LIMIT),
            )
        if isinstance(tail, int) and tail > 0:
            normalized_limit = min(tail, MAX_READ_LINE_LIMIT)
            start = max(1, len(lines) - normalized_limit + 1)
            return _format_chunked_read_result(
                path=relative_path,
                content=content,
                offset=start,
                limit=normalized_limit,
            )
        if len(lines) > DEFAULT_READ_LINE_LIMIT or "offset" in input_data or "limit" in input_data:
            return _format_chunked_read_result(
                path=relative_path,
                content=content,
                offset=max(1, offset),
                limit=min(MAX_READ_LINE_LIMIT, max(1, limit)),
            )
        return _truncate(content)

    return ToolDefinition(
        name="read_file",
        description="Read a UTF-8 text file inside the workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path."},
                "offset": {"type": "number"},
                "limit": {"type": "number"},
                "head": {"type": "number"},
                "tail": {"type": "number"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _list_files_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        relative_path = str(input_data.get("path") or ".")
        root = context.resolve(relative_path)
        if not root.exists():
            return f"List failed: {relative_path} does not exist."
        entries = sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        lines = [
            f"{'[dir]' if item.is_dir() else '[file]'} {item.name}"
            for item in entries[:200]
        ]
        return "\n".join(lines) if lines else "(empty directory)"

    return ToolDefinition(
        name="list_files",
        description="List files and directories inside the workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative directory path."},
            },
            "required": [],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _write_file_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        relative_path = str(input_data["path"])
        target = context.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(input_data["content"]), encoding="utf-8")
        return f"Wrote {relative_path}"

    return ToolDefinition(
        name="write_file",
        description="Write a full text file inside the workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _edit_file_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        relative_path = str(input_data["path"])
        target = context.resolve(relative_path)
        current = target.read_text(encoding="utf-8")
        old_text = str(input_data["oldText"])
        new_text = str(input_data["newText"])
        replace_all = bool(input_data.get("replaceAll"))
        if old_text not in current:
            return f"Edit failed: target text not found in {relative_path}"
        updated = current.replace(old_text, new_text) if replace_all else current.replace(old_text, new_text, 1)
        target.write_text(updated, encoding="utf-8")
        return f"Updated {relative_path}"

    return ToolDefinition(
        name="edit_file",
        description="Replace exact text inside a file.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "oldText": {"type": "string"},
                "newText": {"type": "string"},
                "replaceAll": {"type": "boolean"},
            },
            "required": ["path", "oldText", "newText"],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _glob_files_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        pattern = _normalize_rel_path(str(input_data.get("pattern") or "**/*"))
        matches = []
        for path in context.workspace_root.rglob("*"):
            relative = path.relative_to(context.workspace_root).as_posix()
            if fnmatch(relative, pattern):
                matches.append(relative + ("/" if path.is_dir() else ""))
        if not matches:
            return "(no matches)"
        return _truncate("\n".join(sorted(matches)[:200]))

    return ToolDefinition(
        name="glob_files",
        description="Find files with a glob pattern relative to the workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _grep_files_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        pattern = str(input_data["pattern"])
        case_sensitive = bool(input_data.get("caseSensitive"))
        literal = bool(input_data.get("literal"))
        limit = int(input_data.get("limit") or 100)
        source = re.escape(pattern) if literal else pattern
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(source, flags)
        matches: list[str] = []
        for file_path in context.iter_files():
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            lines = _split_lines(content)
            for line_number, line in enumerate(lines, start=1):
                if regex.search(line):
                    rel = file_path.relative_to(context.workspace_root).as_posix()
                    matches.append(f"{rel}:{line_number}:{line}")
                    if len(matches) >= limit:
                        return _truncate("\n".join(matches))
        if not matches:
            return "(no matches)"
        return _truncate("\n".join(matches))

    return ToolDefinition(
        name="grep_files",
        description="Search for text across workspace files.",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "caseSensitive": {"type": "boolean"},
                "literal": {"type": "boolean"},
                "limit": {"type": "number"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _run_shell_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        command = str(input_data["command"])
        timeout_seconds = float(input_data.get("timeoutSeconds") or 15)
        result = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(context.workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        output = [
            f"exit_code={result.returncode}",
            f"stdout:\n{result.stdout}" if result.stdout else "",
            f"stderr:\n{result.stderr}" if result.stderr else "",
        ]
        return _truncate("\n\n".join(part for part in output if part))

    return ToolDefinition(
        name="run_shell",
        description="Run a shell command inside the workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeoutSeconds": {"type": "number"},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _python_exec_tool(context: WorkspaceToolContext) -> ToolDefinition:
    def execute(input_data: dict[str, Any]) -> str:
        code = str(input_data["code"])
        timeout_seconds = float(input_data.get("timeoutSeconds") or 20)
        run_dir = context.workspace_root / ".super_agent_runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="agent_",
            dir=run_dir,
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write(code)
            script_path = Path(handle.name)
        try:
            result = subprocess.run(
                ["python3", str(script_path)],
                cwd=str(context.workspace_root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        finally:
            script_path.unlink(missing_ok=True)
        output = [
            f"script_path={script_path.name}",
            f"exit_code={result.returncode}",
            f"stdout:\n{result.stdout}" if result.stdout else "",
            f"stderr:\n{result.stderr}" if result.stderr else "",
        ]
        return _truncate("\n\n".join(part for part in output if part))

    return ToolDefinition(
        name="python_exec",
        description="Execute a short Python script inside the workspace and return stdout/stderr.",
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "timeoutSeconds": {"type": "number"},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        execute=execute,
    )


def create_core_tools(workspace_root: str | Path) -> list[ToolDefinition]:
    context = WorkspaceToolContext(Path(workspace_root).resolve())
    return [
        _list_files_tool(context),
        _read_file_tool(context),
        _write_file_tool(context),
        _edit_file_tool(context),
        _glob_files_tool(context),
        _grep_files_tool(context),
        _run_shell_tool(context),
        _python_exec_tool(context),
    ]
