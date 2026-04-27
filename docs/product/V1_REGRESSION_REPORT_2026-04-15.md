# V1 回归报告（2026-04-15）

- 执行时间：2026-04-15T00:35:56
- 隔离工作目录：`/tmp/v1_regression_20260415__7krz9ne`
- 隔离数据库：`/tmp/v1_regression_20260415__7krz9ne/registry.db`

## 1. 基线检查

- `demo.workspace_case.list.default_case_ref` = `workspace/fund_docx_direct_warn`

## 2. direct-match 回归

### workspace/fund_docx_direct_warn

- `scenario_id` = `fund_nav_warning`
- `parser_status` = `parsed_complete`
- `route_decision` = `direct_match`
- `matched_rule_id` = `private_fund.nav_risk_warning.v1`
- `final_decision` = `must_warn`
- `decision_text` = `需要进行风险提示`
- `evidence_count` = `12`
- `auto_status` = `recorded_only`
- `feedback_id` = `None`
- `draft_id` = `None`
- `review_task_id` = `None`
- `trace_id` = `trace_20260414T163336_4fbd7979`
- `final_answer` = 需要做风险提示，因为净值已经跌破合同阈值，且合同明确要求触发后向投资者提示风险。

### workspace/credit_docx_direct_notify

- `scenario_id` = `credit_notice`
- `parser_status` = `parsed_complete`
- `route_decision` = `direct_match`
- `matched_rule_id` = `credit.loan_extension_notice.v1`
- `final_decision` = `needs_more_context`
- `decision_text` = `已识别相关规则，等待补充材料`
- `evidence_count` = `1`
- `auto_status` = `draft_promoted`
- `feedback_id` = `feedback_7e5314b42764`
- `draft_id` = `draft_2753f4f09971`
- `review_task_id` = `review_964d45d8bf8d`
- `trace_id` = `trace_20260414T163405_a1e52146`
- `final_answer` = 系统已命中相关规则，但以下关键字段仍缺失：days_to_maturity。请补充材料后重新提交。

## 3. exploration 回归

### workspace/workspace_known_family_patch_scope

- `scenario_id` = `fund_nav_warning`
- `parser_status` = `parsed_complete`
- `route_decision` = `exploration`
- `final_decision` = `needs_review`
- `decision_text` = `建议先人工复核`
- `auto_status` = `draft_promoted`
- `feedback_id` = `feedback_e8b15dfcc67c`
- `draft_id` = `draft_4796fd1a62e7`
- `review_task_id` = `review_3e6485a72b5b`
- `trace_id` = `trace_20260414T163507_8dfdb907`
- `final_answer` = 当前没有稳定规则可直接给出建议，系统已进入探索路径，建议人工复核并记录反馈。

### workspace/workspace_exploration_new_atomic

- `scenario_id` = `fund_nav_warning`
- `parser_status` = `no_materials`
- `route_decision` = `exploration`
- `final_decision` = `needs_review`
- `decision_text` = `建议先人工复核`
- `auto_status` = `draft_promoted`
- `feedback_id` = `feedback_b72258a6556f`
- `draft_id` = `draft_e4268e2a17e7`
- `review_task_id` = `review_6dd78f16bb6d`
- `trace_id` = `trace_20260414T163538_b79d652e`
- `final_answer` = 当前没有稳定规则可直接给出建议，系统已进入探索路径，建议人工复核并记录反馈。

## 4. review -> publish 回归

- `review_task_id` = `review_3e6485a72b5b`
- `approve_ok` = `True`
- `review_status` = `approved`
- `review_result_note` = `v1_regression_approve`
- `draft_status` = `published`
- `rule_version_count` = `1`
- `latest_rule_version.rule_version_id` = `rule_version_638f49c42129`
- `latest_rule_version.rule_id` = `private_fund.nav_risk_warning.v1`
- `latest_rule_version.source_draft_id` = `draft_4796fd1a62e7`
- `latest_rule_version.status` = `published`

## 5. 快速结论

- direct-match（fund）: PASS
- direct-match（credit）: PASS（修复后）
- exploration -> draft/review: PASS
- review -> publish: PASS

## 6. 修复备注（2026-04-15）

`credit_docx_direct_notify` 最初失败，不是因为核心逻辑损坏，而是因为 demo case 本身缺失了“距离到期日还有 20 天”的材料。

修复动作：

- 为 `demo_cases/workspace/credit_docx_direct_notify/` 补充了 `materials/maturity_schedule.docx`
- 更新了 `input.json`
- 将 `expected.json.parser_status` 从 `parsed_with_defaults` 调整为 `parsed_complete`

修复后针对性回归结果：

- `route_decision = direct_match`
- `final_decision = must_notify`
- `decision_text = 建议发送借款人通知`
- `parser_status = parsed_complete`
- `auto_status = recorded_only`
- `feedback_id = null`

因此，当前可将该 case 重新视为通过。
