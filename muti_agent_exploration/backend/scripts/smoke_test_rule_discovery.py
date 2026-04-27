"""
规则发现后端 smoke test。

运行方式：
    uv run python scripts/smoke_test_rule_discovery.py
"""

import json
import time

from app import create_app


def main() -> None:
    app = create_app()
    client = app.test_client()

    rule_set_resp = client.post(
        '/api/discovery/rule-sets/import',
        json={
            "name": "smoke-rules",
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
    )
    assert rule_set_resp.status_code == 200, rule_set_resp.json
    rule_set_id = rule_set_resp.json["data"]["rule_set_id"]

    document_set_resp = client.post(
        '/api/discovery/documents/import',
        json={
            "name": "smoke-docs",
            "documents": [
                {
                    "title": "doc1",
                    "content": "公司计划在下周发布一则涉及重大合作变化的公告，但当前表述较模糊，可能引发误解。",
                }
            ],
        },
    )
    assert document_set_resp.status_code == 200, document_set_resp.json
    document_set_id = document_set_resp.json["data"]["document_set"]["document_set_id"]

    task_resp = client.post(
        '/api/discovery/tasks/discover-rule',
        json={
            "query": "面对即将发布且表述模糊的重大公告，应适用什么规则？",
            "context": "公告涉及重大合作变化，当前表述较模糊，可能误导外部。",
            "rule_set_id": rule_set_id,
            "document_set_id": document_set_id,
            "use_llm": False,
        },
    )
    assert task_resp.status_code == 200, task_resp.json
    task_id = task_resp.json["data"]["task_id"]

    final_status = None
    for _ in range(30):
        status_resp = client.get(f'/api/discovery/tasks/{task_id}')
        assert status_resp.status_code == 200, status_resp.json
        final_status = status_resp.json["data"]["status"]
        if final_status in {"completed", "failed", "insufficient_evidence", "need_human_review"}:
            break
        time.sleep(0.2)

    result_resp = client.get(f'/api/discovery/tasks/{task_id}/result')
    assert result_resp.status_code == 200, result_resp.json

    result = result_resp.json["data"]
    stages_resp = client.get(f'/api/discovery/tasks/{task_id}/stages')
    assert stages_resp.status_code == 200, stages_resp.json
    stages = stages_resp.json["data"]["stages"]
    assert "problem_frame" in stages, stages
    assert "analogies" in stages, stages

    stage_resp = client.get(f'/api/discovery/tasks/{task_id}/stages/problem_frame')
    assert stage_resp.status_code == 200, stage_resp.json

    logs_resp = client.get(f'/api/discovery/tasks/{task_id}/logs')
    assert logs_resp.status_code == 200, logs_resp.json
    logs = logs_resp.json["data"]["logs"]

    assert result["resolution_type"] in {
        "exact_reuse",
        "adapted_rule",
        "novel_rule",
        "insufficient_evidence",
    }, result
    assert len(logs) >= 5, logs

    print("final_status:", final_status)
    print("resolution_type:", result["resolution_type"])
    print("candidate_count:", len(result.get("candidate_rules", [])))
    print("stage_count:", len(stages))
    print("log_count:", len(logs))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
