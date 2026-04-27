from __future__ import annotations

from typing import Any


SKILL_REGISTRY: dict[str, dict[str, str]] = {
    "compare_numeric": {
        "skill_id": "skill.compare_numeric",
        "label": "数值比较能力",
        "category": "deterministic_tool",
    },
    "boolean_gate": {
        "skill_id": "skill.boolean_gate",
        "label": "布尔门控能力",
        "category": "deterministic_tool",
    },
    "build_policy_answer": {
        "skill_id": "skill.policy_answer_builder",
        "label": "策略答案生成能力",
        "category": "answer_builder",
    },
    "build_notice_answer": {
        "skill_id": "skill.notice_answer_builder",
        "label": "通知答案生成能力",
        "category": "answer_builder",
    },
    "exploration_case_draft_builder": {
        "skill_id": "skill.exploration_case_draft_builder",
        "label": "Exploration Case Draft 生成能力",
        "category": "exploration",
    },
    "exploration_rule_candidate_builder": {
        "skill_id": "skill.exploration_rule_candidate_builder",
        "label": "Exploration Rule Candidate 生成能力",
        "category": "exploration",
    },
    "exploration_pattern_suggester": {
        "skill_id": "skill.exploration_pattern_suggester",
        "label": "Exploration Pattern 建议能力",
        "category": "exploration",
    },
}


def _skill_for_tool(tool_name: str | None) -> dict[str, Any] | None:
    if not tool_name:
        return None
    meta = SKILL_REGISTRY.get(
        tool_name,
        {
            "skill_id": f"skill.{tool_name}",
            "label": tool_name,
            "category": "tool",
        },
    )
    return {
        "skill_id": meta["skill_id"],
        "tool_name": tool_name,
        "label": meta["label"],
        "category": meta["category"],
    }


def _template_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    template_id = contract.get("executor", {}).get("template_id") or f"template.{contract['rule_id']}.{contract['step_id']}"
    output_properties = contract.get("constraints", {}).get("output_schema", {}).get("properties", {})
    return {
        "template_id": template_id,
        "rule_id": contract["rule_id"],
        "step_id": contract["step_id"],
        "goal": contract["goal"],
        "allowed_tools": list(contract.get("executor", {}).get("tool") and [contract["executor"]["tool"]] or []),
        "output_fields": list(output_properties.keys()),
        "validator_ids": list(contract.get("validation", {}).get("validators", [])),
        "failure_routes": list(contract.get("validation", {}).get("on_failure", [])),
    }


def _contract_preview(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": contract.get("step_id"),
        "rule_id": contract.get("rule_id"),
        "goal": contract.get("goal"),
        "step_type": contract.get("step_type"),
        "allowed_tool": contract.get("executor", {}).get("tool"),
        "validator_ids": list(contract.get("validation", {}).get("validators", [])),
        "context_keys": sorted(contract.get("context", {}).keys()),
        "output_fields": sorted(contract.get("constraints", {}).get("output_schema", {}).get("properties", {}).keys()),
    }


def _add_node(nodes: dict[str, dict[str, Any]], node_id: str, node_type: str, label: str, **extra: Any) -> None:
    nodes.setdefault(node_id, {"node_id": node_id, "node_type": node_type, "label": label, **extra})


def _add_edge(edges: dict[tuple[str, str, str], dict[str, Any]], source: str, relation: str, target: str) -> None:
    edges.setdefault((source, relation, target), {"source": source, "relation": relation, "target": target})


def _planner_mode(route_decision: str, exploration_runtime: dict[str, Any] | None, composition_pattern: str | None) -> str:
    if exploration_runtime is not None:
        return "exploration_planner"
    if route_decision == "rule_composable":
        return f"composition_planner:{composition_pattern or 'default'}"
    if route_decision == "direct_match":
        return "direct_rule_planner"
    return "fallback_planner"


def _build_graph_for_contracts(
    *,
    question_packet_preview: dict[str, Any],
    candidate_rules: list[dict[str, Any]],
    templates: list[dict[str, Any]],
    skills: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    question_node_id = "question.current"
    _add_node(nodes, question_node_id, "question", question_packet_preview.get("question_text", "当前问题"))

    for question_type in question_packet_preview.get("question_types", []):
        qtype_id = f"question_type.{question_type}"
        _add_node(nodes, qtype_id, "question_type", question_type)
        _add_edge(edges, question_node_id, "typed_as", qtype_id)
    for intent in question_packet_preview.get("intents", []):
        intent_id = f"intent.{intent}"
        _add_node(nodes, intent_id, "intent", intent)
        _add_edge(edges, question_node_id, "has_intent", intent_id)
    for doc_type in question_packet_preview.get("document_types", []):
        doc_id = f"document_type.{doc_type}"
        _add_node(nodes, doc_id, "document_type", doc_type)
        _add_edge(edges, question_node_id, "targets_document", doc_id)

    rule_ids_in_plan = {item["rule_id"] for item in templates}
    for candidate in candidate_rules:
        if candidate.get("rule_id") not in rule_ids_in_plan:
            continue
        rule_node_id = f"rule.{candidate['rule_id']}"
        _add_node(nodes, rule_node_id, "rule", candidate.get("name") or candidate["rule_id"], rule_kind=candidate.get("rule_kind"))
        for question_type in question_packet_preview.get("question_types", []):
            _add_edge(edges, f"question_type.{question_type}", "retrieves", rule_node_id)
        for intent in question_packet_preview.get("intents", []):
            _add_edge(edges, f"intent.{intent}", "routes_to", rule_node_id)

    for template in templates:
        rule_node_id = f"rule.{template['rule_id']}"
        step_node_id = f"step.{template['rule_id']}.{template['step_id']}"
        template_node_id = f"template.{template['template_id']}"
        _add_node(nodes, step_node_id, "step", template["step_id"])
        _add_node(nodes, template_node_id, "template", template["template_id"])
        _add_edge(edges, rule_node_id, "has_step", step_node_id)
        _add_edge(edges, step_node_id, "compiled_as", template_node_id)

    for skill in skills:
        skill_node_id = f"skill.{skill['skill_id']}"
        _add_node(nodes, skill_node_id, "skill", skill["label"], category=skill["category"])
    for template in templates:
        for tool_name in template.get("allowed_tools", []):
            skill = _skill_for_tool(tool_name)
            if skill is None:
                continue
            step_node_id = f"step.{template['rule_id']}.{template['step_id']}"
            skill_node_id = f"skill.{skill['skill_id']}"
            _add_edge(edges, step_node_id, "uses_skill", skill_node_id)

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }


def _exploration_templates(exploration_runtime: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    templates = [
        {
            "template_id": "template.exploration.case_draft",
            "rule_id": "exploration.case_draft",
            "step_id": "build_case_draft",
            "goal": "生成可沉淀的 case draft",
            "allowed_tools": ["exploration_case_draft_builder"],
            "output_fields": ["case_draft"],
            "validator_ids": ["must_include"],
            "failure_routes": [{"failure_type": "need_more_context", "action": "ask_human", "max_attempts": 1}],
        },
        {
            "template_id": "template.exploration.rule_candidate",
            "rule_id": "exploration.rule_candidate",
            "step_id": "build_candidate_rule_draft",
            "goal": "生成可进入 Rule Factory 的候选规则建议",
            "allowed_tools": ["exploration_rule_candidate_builder"],
            "output_fields": ["candidate_rule_drafts"],
            "validator_ids": ["must_include"],
            "failure_routes": [{"failure_type": "need_human_review", "action": "ask_human", "max_attempts": 1}],
        },
        {
            "template_id": "template.exploration.pattern_suggestion",
            "rule_id": "exploration.pattern_suggestion",
            "step_id": "suggest_patterns",
            "goal": "补充 evidence / validator pattern 建议",
            "allowed_tools": ["exploration_pattern_suggester"],
            "output_fields": ["evidence_pattern_suggestions", "validator_pattern_suggestions"],
            "validator_ids": ["must_include"],
            "failure_routes": [{"failure_type": "low_confidence", "action": "ask_human", "max_attempts": 1}],
        },
    ]
    skills = [_skill_for_tool(tool_name) for tool_name in ["exploration_case_draft_builder", "exploration_rule_candidate_builder", "exploration_pattern_suggester"]]
    return templates, [item for item in skills if item is not None]


def build_orchestration_view(
    *,
    question_packet_preview: dict[str, Any],
    trace_payload: dict[str, Any],
    route_decision: str,
    final_decision: str,
    documents: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
    exploration_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_rules = list(trace_payload.get("retrieval", {}).get("candidates", []))
    contracts = list(trace_payload.get("step_contracts", []))
    if exploration_runtime is not None:
        templates, skills = _exploration_templates(exploration_runtime)
        contract_preview = [
            {
                "step_id": template["step_id"],
                "rule_id": template["rule_id"],
                "goal": template["goal"],
                "step_type": "exploration",
                "allowed_tool": template["allowed_tools"][0],
                "validator_ids": template["validator_ids"],
                "context_keys": ["question_packet", "fact_sheet", "documents"],
                "output_fields": template["output_fields"],
            }
            for template in templates
        ]
    else:
        templates = [_template_from_contract(contract) for contract in contracts]
        skills = []
        seen_skills: set[str] = set()
        for template in templates:
            for tool_name in template.get("allowed_tools", []):
                skill = _skill_for_tool(tool_name)
                if skill is None or skill["skill_id"] in seen_skills:
                    continue
                seen_skills.add(skill["skill_id"])
                skills.append(skill)
        contract_preview = [_contract_preview(contract) for contract in contracts]

    kg_subgraph = _build_graph_for_contracts(
        question_packet_preview=question_packet_preview,
        candidate_rules=candidate_rules,
        templates=templates,
        skills=skills,
    )
    validator_ids = sorted({validator_id for template in templates for validator_id in template.get("validator_ids", [])})
    failure_routes = [route for template in templates for route in template.get("failure_routes", [])]
    composition_plan = trace_payload.get("composition_plan")
    if not isinstance(composition_plan, dict):
        composition_plan = {}
    return {
        "planner": {
            "planner_mode": _planner_mode(route_decision, exploration_runtime, composition_plan.get("composition_pattern")),
            "route_decision": route_decision,
            "final_decision": final_decision,
            "step_count": len(templates),
            "template_count": len(templates),
            "skill_count": len(skills),
            "candidate_rule_count": len(candidate_rules),
        },
        "context_builder": {
            "document_count": len(documents),
            "document_ids": [item.get("doc_id") for item in documents],
            "evidence_count": len(evidence_refs),
            "fact_keys": sorted(question_packet_preview.get("extracted_inputs", {}).keys()),
        },
        "kg_subgraph": kg_subgraph,
        "templates": templates,
        "skills": skills,
        "step_contract_preview": contract_preview,
        "validator_summary": {
            "validator_count": len(validator_ids),
            "validator_ids": validator_ids,
            "failure_routes": failure_routes,
        },
        "prompt_compiler_preview": [
            {
                "template_id": template["template_id"],
                "goal": template["goal"],
                "output_fields": template["output_fields"],
                "allowed_tools": template["allowed_tools"],
            }
            for template in templates
        ],
    }
