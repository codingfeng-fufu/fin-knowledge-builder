from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib import error, request


KimiTransport = Callable[[dict[str, Any]], dict[str, Any]]

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def _load_project_config() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    execute: Callable[[dict[str, Any]], str]


@dataclass(slots=True)
class ProviderResponse:
    content: str
    tool_calls: list[ToolCall]
    raw_response: dict[str, Any]


@dataclass(slots=True)
class AgentRunResult:
    final_text: str
    turns: int
    history: list[dict[str, Any]]
    tool_call_count: int
    agent_trace: list[dict[str, Any]]


def _build_kimi_config() -> dict[str, Any] | None:
    cfg = _load_project_config()
    api_key = (
        cfg.get("moonshot_api_key")
        or os.environ.get("MOONSHOT_API_KEY")
        or os.environ.get("KIMI_API_KEY")
    )
    if not api_key:
        return None
    model = (
        cfg.get("moonshot_model")
        or os.environ.get("MOONSHOT_MODEL")
        or os.environ.get("KIMI_MODEL")
        or "kimi-k2.5"
    )
    temperature = float(
        cfg.get("moonshot_temperature")
        or os.environ.get("MOONSHOT_TEMPERATURE")
        or "0.6"
    )
    if str(model).startswith("kimi-k2.5"):
        temperature = 0.6
    return {
        "api_key": api_key,
        "base_url": cfg.get("moonshot_base_url")
        or os.environ.get("MOONSHOT_BASE_URL")
        or os.environ.get("KIMI_BASE_URL")
        or "https://api.moonshot.ai/v1",
        "model": model,
        "timeout_seconds": float(
            cfg.get("moonshot_timeout_seconds")
            or os.environ.get("MOONSHOT_TIMEOUT_SECONDS")
            or "60"
        ),
        "temperature": temperature,
        "max_tokens": int(
            cfg.get("moonshot_max_tokens")
            or os.environ.get("MOONSHOT_MAX_TOKENS")
            or "4000"
        ),
        "thinking_disabled": (
            os.environ.get("MOONSHOT_THINKING", "disabled").lower() == "disabled"
        ),
    }


def _call_kimi_api(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=f"{config['base_url'].rstrip('/')}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        },
    )
    try:
        with request.urlopen(req, timeout=config["timeout_seconds"]) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Kimi API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Kimi API connection error: {exc}") from exc


def _safe_parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _to_openai_messages(
    *,
    system_prompt: str,
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for item in history:
        role = item.get("role")
        if role == "user":
            messages.append({"role": "user", "content": item.get("content", "")})
            continue
        if role == "assistant":
            message: dict[str, Any] = {
                "role": "assistant",
                "content": item.get("content", ""),
            }
            tool_calls = item.get("tool_calls") or []
            if tool_calls:
                message["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("input", {}), ensure_ascii=False),
                        },
                    }
                    for call in tool_calls
                ]
            messages.append(message)
            continue
        if role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.get("tool_call_id"),
                    "content": item.get("content", ""),
                }
            )
    return messages


def _to_openai_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


def _parse_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    parsed: list[ToolCall] = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        parsed.append(
            ToolCall(
                id=str(call.get("id") or ""),
                name=str(function.get("name") or ""),
                input=_safe_parse_arguments(function.get("arguments")),
            )
        )
    return [call for call in parsed if call.id and call.name]


class KimiSuperAgentProvider:
    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        transport: KimiTransport | None = None,
    ) -> None:
        self._config = config or _build_kimi_config()
        self._transport = transport
        if self._config is None and self._transport is None:
            raise RuntimeError(
                "Super agent requires MOONSHOT_API_KEY/KIMI_API_KEY or an injected transport."
            )

    def respond(
        self,
        *,
        system_prompt: str,
        history: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> ProviderResponse:
        config = self._config or {
            "model": "kimi-k2.5",
            "temperature": 0.1,
            "max_tokens": 4000,
            "thinking_disabled": True,
        }
        payload: dict[str, Any] = {
            "model": config["model"],
            "messages": _to_openai_messages(system_prompt=system_prompt, history=history),
            "tools": _to_openai_tools(tools),
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"],
        }
        if config.get("thinking_disabled", True):
            payload["thinking"] = {"type": "disabled"}
        response = (
            self._transport(payload)
            if self._transport is not None
            else _call_kimi_api(payload, config)
        )
        try:
            message = response["choices"][0]["message"]
        except Exception as exc:
            raise RuntimeError(f"Unexpected Kimi super-agent response shape: {response}") from exc
        content = str(message.get("content") or "")
        return ProviderResponse(
            content=content,
            tool_calls=_parse_tool_calls(message),
            raw_response=response,
        )


def _find_tool(name: str, tools: list[ToolDefinition]) -> ToolDefinition | None:
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def run_agent_loop(
    *,
    provider: KimiSuperAgentProvider,
    tools: list[ToolDefinition],
    system_prompt: str,
    user_message: str,
    max_turns: int = 8,
) -> AgentRunResult:
    history: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    tool_call_count = 0
    agent_trace: list[dict[str, Any]] = [
        {
            "event": "user_message",
            "turn": 0,
            "content": user_message,
        }
    ]
    for turn in range(1, max_turns + 1):
        response = provider.respond(
            system_prompt=system_prompt,
            history=history,
            tools=tools,
        )
        history.append(
            {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "input": dict(call.input)}
                    for call in response.tool_calls
                ],
            }
        )
        agent_trace.append(
            {
                "event": "assistant_response",
                "turn": turn,
                "content": response.content,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "input": dict(call.input)}
                    for call in response.tool_calls
                ],
            }
        )
        if not response.tool_calls:
            return AgentRunResult(
                final_text=response.content.strip(),
                turns=turn,
                history=history,
                tool_call_count=tool_call_count,
                agent_trace=agent_trace,
            )
        for call in response.tool_calls:
            tool_call_count += 1
            tool = _find_tool(call.name, tools)
            if tool is None:
                content = f"Tool not found: {call.name}"
            else:
                try:
                    content = tool.execute(call.input)
                except Exception as exc:
                    content = f"Tool {tool.name} failed: {exc}"
            history.append(
                {
                    "role": "tool",
                    "name": call.name,
                    "tool_call_id": call.id,
                    "content": content,
                }
            )
            agent_trace.append(
                {
                    "event": "tool_result",
                    "turn": turn,
                    "tool_name": call.name,
                    "tool_call_id": call.id,
                    "tool_input": dict(call.input),
                    "content": content,
                }
            )
    final_text = f"Stopped after reaching max_turns={max_turns}."
    history.append({"role": "assistant", "content": final_text, "tool_calls": []})
    return AgentRunResult(
        final_text=final_text,
        turns=max_turns,
        history=history,
        tool_call_count=tool_call_count,
        agent_trace=agent_trace + [
            {
                "event": "stop",
                "turn": max_turns,
                "content": final_text,
            }
        ],
    )
