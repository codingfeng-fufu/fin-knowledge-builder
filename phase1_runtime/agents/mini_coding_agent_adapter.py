from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys
from typing import Any


_MINI_AGENT_REPO_ROOT = Path(__file__).resolve().parents[2] / "mini_coding_agent"


class MiniCodingAgentError(RuntimeError):
    pass


def _load_coding_agent_class() -> Any:
    if not _MINI_AGENT_REPO_ROOT.exists():
        raise MiniCodingAgentError(f"mini coding agent repo not found: {_MINI_AGENT_REPO_ROOT}")
    repo_root = str(_MINI_AGENT_REPO_ROOT.resolve())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from autonomous_coding_agent import CodingAgent  # type: ignore
    except Exception as exc:  # pragma: no cover - import environment dependent
        raise MiniCodingAgentError(f"failed to import mini coding agent: {exc}") from exc
    return CodingAgent


def _build_task_prompt(
    *,
    query: str,
    skill_root: Path,
    workspace_root: Path,
    task_context: dict[str, Any] | None,
    context_packet: dict[str, Any] | None,
) -> str:
    skill_md = (skill_root / "SKILL.md").read_text(encoding="utf-8") if (skill_root / "SKILL.md").exists() else ""
    context_summary = ""
    if context_packet:
        context_summary = str(context_packet.get("context_summary") or "")
    task_context_summary = ""
    if task_context:
        unresolved = task_context.get("unresolved_slots") or []
        if unresolved:
            task_context_summary = f"当前仍待补充字段：{', '.join(str(item) for item in unresolved)}"
    parts = [
        "Use the local coding runtime to solve the following financial workspace task.",
        "Prefer direct file inspection and bounded computation over guessing.",
        "If code execution helps, write only minimal scratch code under the provided workspace.",
        "Do not modify files outside the current workspace root.",
        "",
        f"User query:\n{query}",
        "",
        f"Skill root: {skill_root}",
        f"Workspace root: {workspace_root}",
    ]
    if context_summary:
        parts.extend(["", "Context summary:", context_summary])
    if task_context_summary:
        parts.extend(["", task_context_summary])
    if skill_md:
        parts.extend(["", "Method draft (authoritative guidance):", skill_md])
    parts.extend(
        [
            "",
            "Return the final user-facing answer after completing any necessary computation or scratch-file execution.",
        ]
    )
    return "\n".join(parts)


def run_mini_coding_agent(
    *,
    query: str,
    skill_root: str | Path,
    workspace_root: str | Path,
    task_context: dict[str, Any] | None = None,
    context_packet: dict[str, Any] | None = None,
    max_turns: int = 8,
    provider: str = "auto",
    check_command: str | None = None,
    review_with_agent: bool = False,
) -> dict[str, Any]:
    CodingAgent = _load_coding_agent_class()
    workspace_root_path = Path(workspace_root).resolve()
    skill_root_path = Path(skill_root).resolve()
    if not workspace_root_path.exists():
        raise MiniCodingAgentError(f"workspace root not found: {workspace_root_path}")
    if not skill_root_path.exists():
        raise MiniCodingAgentError(f"skill root not found: {skill_root_path}")

    task_prompt = _build_task_prompt(
        query=query,
        skill_root=skill_root_path,
        workspace_root=workspace_root_path,
        task_context=task_context,
        context_packet=context_packet,
    )
    try:
        relative_scope = skill_root_path.relative_to(workspace_root_path).as_posix()
        write_scopes = [relative_scope or "."]
    except ValueError:
        write_scopes = None

    agent = CodingAgent(
        provider=provider,
        cwd=str(workspace_root_path),
        permission_mode="auto",
        max_turns=max_turns,
    )
    report = agent.deliver_sync(
        task_prompt,
        reset_session=True,
        check_command=check_command,
        allow_writes_under=write_scopes,
        auto_approve=True,
        review_with_agent=review_with_agent,
        include_changed_code=False,
        require_verification=bool(check_command),
    )
    return {
        "query": query,
        "skill_root": str(skill_root_path),
        "skill_md_path": str(skill_root_path / "SKILL.md"),
        "workspace_root": str(workspace_root_path),
        "max_turns": max_turns,
        "turns": 0,
        "tool_call_count": 0,
        "final_text": report.final_text,
        "history": [],
        "context_packet": {} if context_packet is None else context_packet,
        "agent_trace": [],
        "backend": "mini_coding_agent",
        "delivery_result": asdict(report),
        "changed_files": list(report.changed_files),
        "verification": report.verification,
        "review": report.review,
        "review_verdict": report.review_verdict,
    }
