"""
规则发现后端 LLM 稳定性长测脚本。

运行方式：
    uv run python scripts/llm_regression_rule_discovery.py
    uv run python scripts/llm_regression_rule_discovery.py --case grounded_relevant
    uv run python scripts/llm_regression_rule_discovery.py --json-out /tmp/discovery_llm_report.json
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

from app import create_app
from app.config import Config


TERMINAL_STATUSES = {
    "completed",
    "failed",
    "insufficient_evidence",
    "need_human_review",
    "timed_out",
    "cancelled",
}

DISCOVERY_SUCCESS_STATUSES = {
    "completed",
    "insufficient_evidence",
    "need_human_review",
}


CASE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "grounded_relevant": {
        "mode": "grounded",
        "rule_set": {
            "name": "llm-reg-grounded-rules",
            "rules": [
                {
                    "rule_id": "R-001",
                    "title": "披露义务规则",
                    "content": "当公司发布重大事项信息时，应及时披露相关事实。",
                    "conditions": ["公司发布重大事项信息"],
                    "exceptions": ["法律明确禁止披露的情形"],
                    "priority": 10,
                    "source": "规则手册",
                },
                {
                    "rule_id": "R-002",
                    "title": "补充说明规则",
                    "content": "当公开信息存在歧义时，应提供补充说明以避免误导。",
                    "conditions": ["公开信息存在歧义"],
                    "priority": 8,
                    "source": "规则手册",
                },
            ],
        },
        "document_set": {
            "name": "llm-reg-grounded-docs",
            "documents": [
                {
                    "title": "doc1",
                    "content": "公司计划在下周发布一则涉及重大合作变化的公告，但当前表述较模糊，可能引发误解。",
                }
            ],
        },
        "task": {
            "query": "面对即将发布且表述模糊的重大公告，应适用什么规则？",
            "context": "公告涉及重大合作变化，当前表述较模糊，可能误导外部。",
            "use_llm": True,
        },
    },
    "emergent_novel": {
        "mode": "emergent",
        "rule_set": {
            "name": "llm-reg-emergent-rules",
            "rules": [
                {
                    "rule_id": "R-A1",
                    "title": "Branch Naming Policy",
                    "content": "All source code branches must follow the naming convention feature/* or fix/* before merge.",
                    "conditions": ["source code branch management"],
                    "priority": 10,
                    "source": "engineering-policy",
                }
            ],
        },
        "document_set": {
            "name": "llm-reg-emergent-docs",
            "documents": [
                {
                    "title": "doc1",
                    "content": "近期团队开始尝试由AI自动生成对外合作邮件草稿。草稿常会夸大合作确定性，甚至默认写入未确认的交付时间。",
                }
            ],
        },
        "task": {
            "query": "对于AI自动生成的对外合作邮件草稿，在发送前应适用什么规则？",
            "context": "AI草稿可能夸大合作确定性，并写入未确认的交付时间。",
            "use_llm": True,
        },
    },
    "conflict_pressure": {
        "mode": "grounded",
        "rule_set": {
            "name": "llm-reg-conflict-rules",
            "rules": [
                {
                    "rule_id": "R-301",
                    "title": "直接发送允许规则",
                    "content": "在紧急情况下，未经额外审批可直接对外发送更新通知。",
                    "conditions": ["紧急情况下对外发送更新通知"],
                    "priority": 9,
                    "source": "policy-a",
                },
                {
                    "rule_id": "R-302",
                    "title": "未经确认信息禁止规则",
                    "content": "未经确认的事实信息不得直接对外发送。",
                    "conditions": ["对外发送未经确认信息"],
                    "priority": 10,
                    "source": "policy-b",
                },
            ],
        },
        "document_set": {
            "name": "llm-reg-conflict-docs",
            "documents": [
                {
                    "title": "纪要",
                    "content": "团队拟通过AI生成紧急对外说明。草稿中包含未经确认的恢复时间与外部影响范围。如果直接发送，可能造成对外误导。",
                }
            ],
        },
        "task": {
            "query": "对于AI生成的紧急对外说明，在发送前应适用什么规则？",
            "context": "草稿中包含未经确认的恢复时间与影响范围，如果直接发送可能误导外部。",
            "use_llm": True,
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run long LLM regression checks for discovery backend.")
    parser.add_argument("--case", action="append", dest="cases", help="Case name to run. Can be passed multiple times.")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Per-task timeout passed into discovery metadata.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--json-out", type=str, help="Optional path to write the final report JSON.")
    return parser.parse_args()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def build_stage_metrics(logs: List[Dict[str, Any]], task_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    ordered_entries: List[Dict[str, Any]] = []
    seen = set()
    for entry in logs:
        stage = entry.get("stage")
        if not stage or stage in seen:
            continue
        seen.add(stage)
        ordered_entries.append(entry)

    metrics: List[Dict[str, Any]] = []
    for index, entry in enumerate(ordered_entries):
        start_at = parse_iso(entry.get("timestamp"))
        if not start_at:
            continue
        if index + 1 < len(ordered_entries):
            end_at = parse_iso(ordered_entries[index + 1].get("timestamp"))
        else:
            end_at = parse_iso(task_data.get("completed_at")) or parse_iso(task_data.get("updated_at"))
        duration = None
        if end_at:
            duration = round((end_at - start_at).total_seconds(), 3)
        metrics.append(
            {
                "stage": entry.get("stage"),
                "start_at": entry.get("timestamp"),
                "end_at": end_at.isoformat() if end_at else None,
                "duration_seconds": duration,
            }
        )
    return metrics


def fetch_result_with_retry(client: Any, task_id: str, attempts: int = 5, delay: float = 0.5) -> Any:
    last_response = None
    for _ in range(attempts):
        response = client.get(f"/api/discovery/tasks/{task_id}/result")
        last_response = response
        if response.status_code == 200:
            return response
        time.sleep(delay)
    return last_response


def is_discovery_success(task_status: str, result_data: Dict[str, Any] | None) -> bool:
    return task_status in DISCOVERY_SUCCESS_STATUSES and result_data is not None


def run_case(client: Any, case_name: str, case: Dict[str, Any], timeout_seconds: int, poll_interval: float) -> Dict[str, Any]:
    rule_set_resp = client.post("/api/discovery/rule-sets/import", json=case["rule_set"])
    assert rule_set_resp.status_code == 200, rule_set_resp.json
    rule_set_id = rule_set_resp.json["data"]["rule_set_id"]

    document_set_resp = client.post("/api/discovery/documents/import", json=case["document_set"])
    assert document_set_resp.status_code == 200, document_set_resp.json
    document_set_id = document_set_resp.json["data"]["document_set"]["document_set_id"]

    task_payload = dict(case["task"])
    task_payload.update(
        {
            "rule_set_id": rule_set_id,
            "document_set_id": document_set_id,
            "discovery_mode": case["mode"],
            "metadata": {"timeout_seconds": timeout_seconds},
        }
    )
    task_resp = client.post("/api/discovery/tasks/discover-rule", json=task_payload)
    assert task_resp.status_code == 200, task_resp.json
    task_id = task_resp.json["data"]["task_id"]

    start = time.time()
    task_data = task_resp.json["data"]
    while True:
        status_resp = client.get(f"/api/discovery/tasks/{task_id}")
        assert status_resp.status_code == 200, status_resp.json
        task_data = status_resp.json["data"]
        if task_data["status"] in TERMINAL_STATUSES:
            break
        time.sleep(poll_interval)

    elapsed = round(time.time() - start, 3)
    result_resp = fetch_result_with_retry(client, task_id)
    logs_resp = client.get(f"/api/discovery/tasks/{task_id}/logs")
    stages_resp = client.get(f"/api/discovery/tasks/{task_id}/stages")

    logs = logs_resp.json["data"]["logs"] if logs_resp.status_code == 200 else []
    stage_names = stages_resp.json["data"]["stages"] if stages_resp.status_code == 200 else []
    stage_metrics = build_stage_metrics(logs, task_data)

    result_data = result_resp.json["data"] if result_resp is not None and result_resp.status_code == 200 else None
    success = is_discovery_success(task_data["status"], result_data)

    candidate_count = len(result_data.get("candidate_rules", [])) if result_data else 0
    summary = result_data.get("summary") if result_data else None
    error = task_data.get("error")
    success_reason = (
        "任务达到发现型终态并成功返回结构化结果。"
        if success
        else "任务未能成功完成发现链路或未返回结果。"
    )

    return {
        "case": case_name,
        "mode": case["mode"],
        "task_id": task_id,
        "status": task_data["status"],
        "has_result": result_data is not None,
        "success_reason": success_reason,
        "resolution_type": result_data.get("resolution_type") if result_data else None,
        "candidate_count": candidate_count,
        "need_human_review": result_data.get("need_human_review") if result_data else None,
        "elapsed_seconds": elapsed,
        "stage_count": len(stage_names),
        "stage_metrics": stage_metrics,
        "log_count": len(logs),
        "summary": summary,
        "error": error,
        "success": success,
    }


def main() -> None:
    args = parse_args()

    if not Config.LLM_API_KEY:
        raise SystemExit("LLM_API_KEY 未配置，无法运行 LLM 长测。")

    case_names = args.cases or list(CASE_DEFINITIONS.keys())
    for name in case_names:
        if name not in CASE_DEFINITIONS:
            raise SystemExit(f"未知 case: {name}")

    app = create_app()
    client = app.test_client()

    report = {
        "started_at": datetime.now().isoformat(),
        "llm_base_url": Config.LLM_BASE_URL,
        "llm_model": Config.LLM_MODEL_NAME,
        "timeout_seconds": args.timeout_seconds,
        "poll_interval": args.poll_interval,
        "cases": [],
    }

    overall_success = True
    for case_name in case_names:
        case_report = run_case(
            client=client,
            case_name=case_name,
            case=CASE_DEFINITIONS[case_name],
            timeout_seconds=args.timeout_seconds,
            poll_interval=args.poll_interval,
        )
        report["cases"].append(case_report)
        overall_success = overall_success and case_report["success"]

    report["finished_at"] = datetime.now().isoformat()
    report["overall_success"] = overall_success

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not overall_success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
