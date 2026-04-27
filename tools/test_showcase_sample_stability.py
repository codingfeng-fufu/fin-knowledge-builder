from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path


API = "http://127.0.0.1:8010/api/phase1"
CASE_REF = "workspace/equity_research_h3_code_upside_calc"
RUN_COUNT = 3
TIMEOUT_SECONDS = 240
OUTPUT_DIR = Path("contest/beijing_ai_track_upload_package/showcase_sample_runs")


def post(payload: dict, timeout: int = TIMEOUT_SECONDS) -> dict:
    request = urllib.request.Request(
        API,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def is_acceptable(data: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    route_decision = data.get("route_decision")
    final_decision = data.get("final_decision")
    display_decision_text = data.get("display_decision_text")
    final_answer = str(data.get("final_answer") or "")

    if route_decision != "direct_match":
        reasons.append(f"route_decision={route_decision}")
    if final_decision != "audit_completed":
        reasons.append(f"final_decision={final_decision}")
    if display_decision_text != "已完成核验":
        reasons.append(f"display_decision_text={display_decision_text}")

    required_sections = [
        "### 1. 关键信息提取",
        "### 2. Python 代码",
        "### 3. 核验结论",
        "### 4. 三句话总结",
    ]
    for section in required_sections:
        if section not in final_answer:
            reasons.append(f"missing_section={section}")

    disallowed_fragments = [
        "当前没有稳定规则可直接给出建议",
        "建议人工复核",
        "未稳定提取到完整表格",
        "未稳定提取到明确风险提示",
    ]
    for fragment in disallowed_fragments:
        if fragment in final_answer:
            reasons.append(f"contains_disallowed={fragment}")

    return not reasons, reasons


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sample_resp = post({"action": "demo.workspace_case.get", "case_ref": CASE_REF}, timeout=60)
    sample = sample_resp["data"]

    summary: list[dict] = []
    for index in range(1, RUN_COUNT + 1):
        print(f"[run {index}] starting...", flush=True)
        started = time.time()
        solve_resp = post(
            {
                "action": "product.workspace.solve",
                "question_text": sample["question_text"],
                "scenario_id": sample["scenario_id"],
                "materials": sample["materials"],
                "metadata": {
                    "use_live_kimi": False,
                    "run_live_super_agent": False,
                    "exploration_use_llm": False,
                    "exploration_mode": "grounded",
                },
            },
            timeout=TIMEOUT_SECONDS,
        )
        elapsed = round(time.time() - started, 2)
        data = solve_resp.get("data") or {}
        ok, reasons = is_acceptable(data)

        run_record = {
            "run_index": index,
            "elapsed_seconds": elapsed,
            "acceptable": ok,
            "reasons": reasons,
            "route_decision": data.get("route_decision"),
            "display_decision_text": data.get("display_decision_text"),
            "final_decision": data.get("final_decision"),
            "answer_engine": data.get("answer_engine"),
            "question_text": data.get("question_text"),
            "final_answer": data.get("final_answer"),
        }
        out_path = OUTPUT_DIR / f"run_{index:02d}.json"
        out_path.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "run": index,
                    "elapsed_seconds": elapsed,
                    "acceptable": ok,
                    "route_decision": data.get("route_decision"),
                    "display_decision_text": data.get("display_decision_text"),
                    "final_decision": data.get("final_decision"),
                    "reasons": reasons,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        summary.append(run_record)

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    passed = all(item["acceptable"] for item in summary)
    print(json.dumps({"all_passed": passed, "summary_path": str(summary_path)}, ensure_ascii=False), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
