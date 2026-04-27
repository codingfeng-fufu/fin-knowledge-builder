from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable
from urllib import error, request


KimiTransport = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class KimiSkillCreatorConfig:
    api_key: str
    base_url: str = "https://api.moonshot.ai/v1"
    model: str = "kimi-k2.5"
    timeout_seconds: float = 30.0
    thinking_disabled: bool = True
    temperature: float = 0.2
    max_tokens: int = 3000

    @classmethod
    def from_env(cls) -> "KimiSkillCreatorConfig | None":
        api_key = os.environ.get("MOONSHOT_API_KEY")
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            base_url=os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1"),
            model=os.environ.get("MOONSHOT_MODEL", "kimi-k2.5"),
            timeout_seconds=float(os.environ.get("MOONSHOT_TIMEOUT_SECONDS", "30")),
            thinking_disabled=os.environ.get("MOONSHOT_THINKING", "disabled").lower() == "disabled",
            temperature=float(os.environ.get("MOONSHOT_TEMPERATURE", "0.2")),
            max_tokens=int(os.environ.get("MOONSHOT_MAX_TOKENS", "3000")),
        )


def build_kimi_skill_creator_messages(skill_request: dict[str, Any]) -> list[dict[str, str]]:
    system_prompt = str(skill_request["system_prompt"])
    skill_creator_reference = skill_request.get("skill_creator_reference_md")
    user_payload = {
        "instruction": skill_request["user_prompt"],
        "query": skill_request.get("query"),
        "constraints": skill_request.get("constraints", {}),
        "rule": skill_request.get("rule", {}),
        "task_context": skill_request.get("task_context", {}),
        "rule_binding": skill_request.get("rule_binding", {}),
        "output_contract": {
            "skill_name": "string",
            "description": "string",
            "skill_md": "string",
            "references": "object<string,string>",
            "scripts": "object<string,string>",
        },
    }
    if isinstance(skill_creator_reference, str) and skill_creator_reference.strip():
        user_payload["skill_creator_reference_md"] = skill_creator_reference
    user_prompt = (
        "Return exactly one JSON object and no extra prose.\n"
        "The JSON must contain keys: skill_name, description, skill_md, references, scripts.\n"
        "The SKILL.md body must follow the installed skill-creator structure and stay concise.\n\n"
        f"{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_kimi_chat_payload(skill_request: dict[str, Any], config: KimiSkillCreatorConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": build_kimi_skill_creator_messages(skill_request),
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    if config.thinking_disabled:
        payload["thinking"] = {"type": "disabled"}
    return payload


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def _call_kimi_api(payload: dict[str, Any], config: KimiSkillCreatorConfig) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=f"{config.base_url.rstrip('/')}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
    )
    try:
        with request.urlopen(req, timeout=config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:  # pragma: no cover - network path
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Kimi API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:  # pragma: no cover - network path
        raise RuntimeError(f"Kimi API connection error: {exc}") from exc


def build_kimi_llm_generate(
    *,
    config: KimiSkillCreatorConfig | None = None,
    transport: KimiTransport | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    resolved_config = config or KimiSkillCreatorConfig.from_env()
    if resolved_config is None:
        raise RuntimeError("MOONSHOT_API_KEY is not configured")

    def _generate(skill_request: dict[str, Any]) -> dict[str, Any]:
        payload = build_kimi_chat_payload(skill_request, resolved_config)
        response = transport(payload) if transport is not None else _call_kimi_api(payload, resolved_config)
        try:
            content = response["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"Unexpected Kimi response shape: {response}") from exc
        generated = _extract_json_object(content)
        generated.setdefault("references", {})
        generated.setdefault("scripts", {})
        return generated

    return _generate
