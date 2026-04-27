from __future__ import annotations

from pathlib import Path
from typing import Any

from ..factory import merge_rules_for_runtime
from ..parsing import get_document_parser_contract
from ..prototype.prototype_service import (
    CREDIT_ATOMIC_RULE_FIXTURES,
    CREDIT_DATASET_DIR,
    EQUITY_RESEARCH_DATASET_DIR,
    FUND_ATOMIC_RULE_FIXTURES,
    FUND_DATASET_DIR,
    PROTOTYPE_FLOWS,
    _load_materials,
)
from ..registry.registry_store import DEFAULT_DB_PATH
from ..schema import load_document_bundle, load_question, load_rule


DEFAULT_PRODUCT_WORK_DIR = Path("phase1_runtime/product_runs")
WORKSPACE_ENTRY_PATH = "/workspace"
FUND_FULL_RULE_PATH = Path("phase1_runtime/fixtures/rule_private_fund_nav_warning.json")
CREDIT_FULL_RULE_PATH = Path("phase1_runtime/fixtures/rule_credit_loan_extension_notice.json")
EQUITY_RESEARCH_FULL_RULE_PATH = Path("phase1_runtime/fixtures/rule_equity_research_full_analysis.json")
EQUITY_RESEARCH_RATING_TARGET_AUDIT_RULE_PATH = Path("phase1_runtime/fixtures/rule_equity_research_rating_target_audit.json")
EQUITY_RESEARCH_RATING_VIEW_RULE_PATH = Path("phase1_runtime/fixtures/rule_equity_research_rating_view.json")
EQUITY_RESEARCH_TARGET_PRICE_VIEW_RULE_PATH = Path("phase1_runtime/fixtures/rule_equity_research_target_price_view.json")
EQUITY_RESEARCH_KEY_RISKS_VIEW_RULE_PATH = Path("phase1_runtime/fixtures/rule_equity_research_key_risks_view.json")
EQUITY_RESEARCH_RISK_COUNT_VIEW_RULE_PATH = Path("phase1_runtime/fixtures/rule_equity_research_risk_count_view.json")
SCENARIO_RULE_PATHS: dict[str, list[Path]] = {
    "fund_nav_warning": [FUND_FULL_RULE_PATH, *FUND_ATOMIC_RULE_FIXTURES],
    "credit_notice": [CREDIT_FULL_RULE_PATH, *CREDIT_ATOMIC_RULE_FIXTURES],
    "equity_research": [
        EQUITY_RESEARCH_RATING_TARGET_AUDIT_RULE_PATH,
        EQUITY_RESEARCH_FULL_RULE_PATH,
        EQUITY_RESEARCH_RATING_VIEW_RULE_PATH,
        EQUITY_RESEARCH_TARGET_PRICE_VIEW_RULE_PATH,
        EQUITY_RESEARCH_KEY_RISKS_VIEW_RULE_PATH,
        EQUITY_RESEARCH_RISK_COUNT_VIEW_RULE_PATH,
    ],
    "equity_research_adjudication": [],
    "disclosure_clarification": [],
}

PRODUCT_SCENARIOS: dict[str, dict[str, Any]] = {
    "fund_nav_warning": {
        "scenario_id": "fund_nav_warning",
        "title": "基金净值预警",
        "description": "针对净值跌破阈值后是否需要向投资者提示风险的处理方案。",
        "flow_id": "fund_compose",
        "source_dataset_dir": FUND_DATASET_DIR,
        "keywords": ["净值", "基金", "投资者", "风险提示", "阈值"],
    },
    "credit_notice": {
        "scenario_id": "credit_notice",
        "title": "信贷通知判断",
        "description": "针对是否需要向借款人发送通知的处理方案。",
        "flow_id": "credit_compose",
        "source_dataset_dir": CREDIT_DATASET_DIR,
        "keywords": ["借款人", "通知", "展期", "续贷", "贷款", "到期"],
    },
    "equity_research": {
        "scenario_id": "equity_research",
        "title": "股票研报分析",
        "description": "针对个股研报提取评级、目标价和主要下行风险的综合分析。",
        "flow_id": "equity_research_direct",
        "source_dataset_dir": EQUITY_RESEARCH_DATASET_DIR,
        "keywords": ["研报", "评级", "目标价", "增持", "买入", "分析师", "证券研究报告", "公司简评", "投资要点"],
    },
    "equity_research_adjudication": {
        "scenario_id": "equity_research_adjudication",
        "title": "研报观点冲突裁决",
        "description": "针对研报是否应按现有评级正式发布、支持与反对证据如何裁决的探索型审查。",
        "flow_id": "equity_research_direct",
        "source_dataset_dir": EQUITY_RESEARCH_DATASET_DIR,
        "keywords": ["研报", "裁决", "发布", "质控", "复核", "反证", "支持方", "反对方", "改写"],
    },
    "disclosure_clarification": {
        "scenario_id": "disclosure_clarification",
        "title": "公告披露澄清",
        "description": "针对重大公告发布前后的表述澄清、对外措辞和适用规则判断。",
        "flow_id": "fund_compose",
        "source_dataset_dir": FUND_DATASET_DIR,
        "keywords": ["公告", "披露", "澄清", "误导", "重大事项", "重大合作", "表述模糊"],
    },
}

DECISION_TEXT_MAP = {
    "must_warn": "需要进行风险提示",
    "needs_review": "建议先人工复核",
    "needs_more_context": "已识别相关规则，等待补充材料",
    "must_notify": "建议发送借款人通知",
    "no_notice_required": "当前无需发送通知",
    "rating_bullish": "研报观点偏积极",
    "rating_neutral": "研报观点中性",
    "rating_bearish": "研报观点偏谨慎",
    "upside_high": "目标价上行空间较高",
    "upside_moderate": "目标价上行空间中等",
    "upside_low": "目标价上行空间有限",
    "risks_multiple": "研报列出了多项下行风险",
    "risks_limited": "研报列出的下行风险较少",
    "risks_not_found": "研报中未明确列出下行风险",
    "risk_count_answered": "已统计出主要下行风险数量",
    "audit_completed": "已完成核验",
}

ROUTE_TITLE_MAP = {
    "direct_match": "规则直接复用",
    "rule_composable": "规则复用与组合",
    "needs_more_context": "已识别相关规则，等待补充材料",
    "exploration": "多智能体探索",
}

ROUTE_GUIDANCE_MAP = {
    "direct_match": "本次问题已命中稳定规则，系统优先复用已有规则给出结论。",
    "rule_composable": "本次问题由多个规则单元组合得出建议，说明已有能力已经可以被复用并继续组合。",
    "needs_more_context": "系统已识别到适用规则，但文档中缺少部分必要信息，请补充相关材料后重新提交。",
    "exploration": "本次问题未命中稳定规则，系统已转入多智能体探索与后续规则生长流程。",
}

FACTORY_NEXT_STEP_MAP = {
    "direct_match": "保留 trace 与执行证据，作为后续复核与审计依据。",
    "rule_composable": "优先把这次稳定组合沉淀为 composite rule，减少后续重复组合。",
    "needs_more_context": "引导用户补充缺失材料，重新提交后系统将再次尝试匹配规则。",
    "exploration": "优先记录 feedback，并把多智能体探索产出的候选规则继续送入草稿、审核与发布流程。",
}


def get_workspace_contract() -> dict[str, Any]:
    parser_contract = get_document_parser_contract()
    return {
        "entry_path": WORKSPACE_ENTRY_PATH,
        "entry_title": "金融规则资产专家工作台",
        "entry_role": "expert_workbench",
        "entry_summary": "这是当前系统的主入口。它负责接收问题与材料，输出建议，并把运行结果继续送向 Rule Factory。",
        "parser_status": parser_contract["status"],
        "parser_contract_version": parser_contract["contract_version"],
        "main_loop": [
            "问题与材料进入工作台",
            "文档解析器生成 question_packet / fact_sheet / evidence_packets",
            "runtime 执行 direct match / composition / exploration",
            "trace 与 feedback 回流到 Rule Factory",
        ],
        "document_parser_contract": parser_contract,
    }


def list_product_scenarios() -> dict[str, Any]:
    items = []
    for scenario_id, config in PRODUCT_SCENARIOS.items():
        flow = PROTOTYPE_FLOWS[config["flow_id"]]
        materials = _load_materials(Path(flow["source_dataset_dir"]))
        items.append(
            {
                "scenario_id": scenario_id,
                "title": config["title"],
                "description": config["description"],
                "default_question_text": materials["question_text"],
                "documents": materials["documents"],
                "evidence_count": materials["evidence_count"],
            }
        )
    return {
        "scenario_count": len(items),
        "default_scenario_id": "fund_nav_warning",
        "scenarios": items,
        "workspace_entry": get_workspace_contract(),
    }


def build_expert_view(*, scenario_id: str, question_text: str, final_answer: str, final_decision: str, route_decision: str) -> dict[str, Any]:
    return {
        "workspace_role": "专家工作台",
        "primary_entry": WORKSPACE_ENTRY_PATH,
        "question_text": question_text,
        "decision_text": DECISION_TEXT_MAP.get(final_decision, final_decision),
        "route_title": ROUTE_TITLE_MAP.get(route_decision, route_decision),
        "route_guidance": ROUTE_GUIDANCE_MAP.get(route_decision, route_decision),
        "next_factory_step": FACTORY_NEXT_STEP_MAP.get(route_decision, "保留 trace 并等待下一步处理。"),
        "recommended_answer": final_answer,
        "scenario_id": scenario_id,
    }


def scenario_seed_bundle(scenario_id: str) -> dict[str, Any]:
    dataset_dir = Path(PRODUCT_SCENARIOS[scenario_id]["source_dataset_dir"])
    question = load_question(dataset_dir / "question_struct.json")
    facts, evidence_refs = load_document_bundle(dataset_dir / "document_bundle.json")
    materials = _load_materials(dataset_dir)
    return {
        "dataset_dir": dataset_dir,
        "question": question,
        "facts": facts,
        "evidence_refs": evidence_refs,
        "documents": materials["documents"],
        "case_id": materials["case_id"],
        "case_title": materials["case_title"],
    }


def normalize_materials(materials: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if materials is None:
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(materials, start=1):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or f"material_{index}"
        normalized.append(
            {
                "name": str(name),
                "content": str(item.get("content") or "") if item.get("content") is not None else "",
                "content_base64": str(item.get("content_base64")) if item.get("content_base64") is not None else None,
                "media_type": str(item.get("media_type")) if item.get("media_type") is not None else None,
                "size": int(item.get("size")) if item.get("size") is not None else None,
            }
        )
    return normalized


def _material_text_for_inference(material: dict[str, Any]) -> str:
    content = str(material.get("content", ""))
    if content.strip():
        return content
    line_items = material.get("line_items")
    if isinstance(line_items, list) and line_items:
        return "\n".join(str(item.get("text", "")).strip() for item in line_items if str(item.get("text", "")).strip())
    return ""


def infer_scenario(question_text: str, materials: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    combined = "\n".join([question_text, *[_material_text_for_inference(item) for item in materials]]).lower()
    scores: dict[str, int] = {}
    matched_keywords: dict[str, list[str]] = {}
    for scenario_id, config in PRODUCT_SCENARIOS.items():
        keywords = config["keywords"]
        hits = [keyword for keyword in keywords if keyword.lower() in combined]
        matched_keywords[scenario_id] = hits
        scores[scenario_id] = len(hits)

    best = max(scores.items(), key=lambda item: item[1])
    scenario_id = best[0] if best[1] > 0 else "fund_nav_warning"
    return scenario_id, {
        "scores": scores,
        "matched_keywords": matched_keywords,
        "selected_scenario_id": scenario_id,
        "mode": "auto_infer",
    }
