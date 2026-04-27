from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .super_agent import KimiSuperAgentProvider, run_agent_loop
from .mini_coding_agent_adapter import run_mini_coding_agent
from .super_agent_tools import create_core_tools


def _load_skill_file_map(skill_root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_root).as_posix()
        if relative == "SKILL.md":
            continue
        files[relative] = str(path)
    return files


def _visible_skill_file_map(skill_file_map: dict[str, str]) -> dict[str, str]:
    visible: dict[str, str] = {}
    for relative, path in skill_file_map.items():
        if relative == "references/bound-context.json":
            continue
        if relative == "references/rule-binding.json":
            continue
        visible[relative] = path
    return visible


def build_super_agent_system_prompt(
    *,
    skill_root: str | Path,
    skill_md: str,
    workspace_root: str | Path,
    task_context: dict[str, Any] | None = None,
    context_packet: dict[str, Any] | None = None,
) -> str:
    context_summary = "{}"
    if task_context:
        context_summary = json.dumps(task_context, ensure_ascii=False, indent=2)
    query_context_summary = "{}"
    if context_packet:
        compact_context = {
            "document_profile": context_packet.get("document_profile", {}),
            "query_profile": context_packet.get("query_profile", {}),
            "context_summary": context_packet.get("context_summary", ""),
            "context_gaps": context_packet.get("context_gaps", []),
            "evidence_units": list((context_packet.get("evidence_units") or [])[:6]),
            "fact_candidates": list((context_packet.get("fact_candidates") or [])[:8]),
        }
        query_context_summary = json.dumps(compact_context, ensure_ascii=False, indent=2)
    return (
        "You are a lightweight coding super agent for a financial rule asset platform.\n"
        "You execute tasks by following the provided runtime skill, inspecting local files, and using tools.\n"
        "Be precise, pragmatic, and concise.\n"
        "Do not invent facts not supported by files or tool outputs.\n"
        "Treat the QUERY-AWARE CONTEXT PACKET as the primary source of truth for answering.\n"
        "If the context packet already contains enough evidence, answer directly without using tools.\n"
        "Only use tools when the context packet is insufficient, when exact file inspection is still needed, or when computation is required.\n"
        "Do not reread bound-context.json or rule-binding.json unless the context packet is clearly insufficient.\n"
        "When answering, the first sentence must be the shortest direct answer to the user's question.\n"
        "After the first sentence, add only the minimum necessary supporting detail.\n"
        "When you have enough evidence, stop using tools and return the final answer.\n"
        "If you change files, mention them in the final answer.\n\n"
        f"SKILL_ROOT: {Path(skill_root).resolve()}\n"
        f"WORKSPACE_ROOT: {Path(workspace_root).resolve()}\n\n"
        "RUNTIME SKILL (authoritative instructions):\n"
        f"{skill_md}\n\n"
        "BOUND TASK CONTEXT SUMMARY:\n"
        f"{context_summary}\n\n"
        "QUERY-AWARE CONTEXT PACKET:\n"
        f"{query_context_summary}"
    )


def build_super_agent_user_message(
    *,
    query: str,
    skill_root: str | Path,
    workspace_root: str | Path,
    skill_file_map: dict[str, str],
    context_packet: dict[str, Any] | None = None,
) -> str:
    visible_skill_file_map = _visible_skill_file_map(skill_file_map)
    visible_inventory = "\n".join(f"- {name}" for name in sorted(visible_skill_file_map)) or "- (no extra files)"
    context_hint = ""
    if context_packet:
        relevant_blocks = context_packet.get("relevant_blocks") or []
        context_hint = (
            "\nUse this query-aware context first:\n"
            + "\n".join(
                f"- p{item.get('locator', {}).get('page', '?')}: {str(item.get('text', ''))[:120]}"
                for item in relevant_blocks[:5]
            )
        )
    return (
        f"Query:\n{query}\n\n"
        "Execute this query using the runtime skill.\n"
        "Prefer answering directly from the query-aware context packet when it is sufficient.\n"
        "Inspect files only if the current context is not enough.\n"
        f"Skill root: {Path(skill_root).resolve()}\n"
        f"Workspace root: {Path(workspace_root).resolve()}\n"
        "Visible skill artifact files:\n"
        f"{visible_inventory}"
        f"{context_hint}"
    )


def build_super_agent_handoff(
    *,
    query: str,
    skill_root: str | Path,
    workspace_root: str | Path,
    task_context: dict[str, Any] | None = None,
    context_packet: dict[str, Any] | None = None,
    max_turns: int = 8,
    backend: str = "builtin",
    coding_agent_check_command: str | None = None,
    coding_agent_review_with_agent: bool = False,
    coding_agent_provider: str = "auto",
) -> dict[str, Any]:
    return {
        "action": "super_agent.run",
        "payload": {
            "query": query,
            "skill_root": str(Path(skill_root).resolve()),
            "workspace_root": str(Path(workspace_root).resolve()),
            "task_context": {} if task_context is None else task_context,
            "context_packet": {} if context_packet is None else context_packet,
            "max_turns": max_turns,
            "backend": backend,
            "coding_agent_check_command": coding_agent_check_command,
            "coding_agent_review_with_agent": coding_agent_review_with_agent,
            "coding_agent_provider": coding_agent_provider,
        },
    }


def run_super_agent(
    *,
    query: str,
    skill_root: str | Path,
    workspace_root: str | Path,
    task_context: dict[str, Any] | None = None,
    context_packet: dict[str, Any] | None = None,
    max_turns: int = 8,
    kimi_client: Any | None = None,
    backend: str = "builtin",
    coding_agent_check_command: str | None = None,
    coding_agent_review_with_agent: bool = False,
    coding_agent_provider: str = "auto",
) -> dict[str, Any]:
    skill_root_path = Path(skill_root).resolve()
    if not skill_root_path.exists():
        raise FileNotFoundError(f"skill root not found: {skill_root_path}")
    skill_md_path = skill_root_path / "SKILL.md"
    if not skill_md_path.exists():
        raise FileNotFoundError(f"SKILL.md not found under {skill_root_path}")

    if backend == "mini_coding_agent":
        return run_mini_coding_agent(
            query=query,
            skill_root=skill_root_path,
            workspace_root=workspace_root,
            task_context=task_context,
            context_packet=context_packet,
            max_turns=max_turns,
            provider=coding_agent_provider,
            check_command=coding_agent_check_command,
            review_with_agent=coding_agent_review_with_agent,
        )
    if backend != "builtin":
        raise ValueError(f"unsupported super agent backend: {backend}")

    skill_md = skill_md_path.read_text(encoding="utf-8")
    skill_file_map = _load_skill_file_map(skill_root_path)
    system_prompt = build_super_agent_system_prompt(
        skill_root=skill_root_path,
        skill_md=skill_md,
        workspace_root=workspace_root,
        task_context=task_context,
        context_packet=context_packet,
    )
    user_message = build_super_agent_user_message(
        query=query,
        skill_root=skill_root_path,
        workspace_root=workspace_root,
        skill_file_map=skill_file_map,
        context_packet=context_packet,
    )
    provider = KimiSuperAgentProvider(transport=kimi_client)
    tools = create_core_tools(workspace_root)
    result = run_agent_loop(
        provider=provider,
        tools=tools,
        system_prompt=system_prompt,
        user_message=user_message,
        max_turns=max_turns,
    )
    return {
        "query": query,
        "skill_root": str(skill_root_path),
        "skill_md_path": str(skill_md_path),
        "workspace_root": str(Path(workspace_root).resolve()),
        "max_turns": max_turns,
        "turns": result.turns,
        "tool_call_count": result.tool_call_count,
        "final_text": result.final_text,
        "history": result.history,
        "context_packet": {} if context_packet is None else context_packet,
        "agent_trace": result.agent_trace,
    }
