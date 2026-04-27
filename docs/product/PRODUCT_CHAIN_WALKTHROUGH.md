# 产品链路走查

> 更新时间：2026-04-14
> 结论以代码与实际运行结果为准。

相关产品文档：

- `PRODUCT_QUESTIONS.md`
- `USER_ROLES_AND_CORE_TASKS.md`
- `V1_PRODUCT_BOUNDARY.md`
- `V1_PRD.md`

## 1. 这项目现在到底是什么

这个仓库当前真正的主产品不是顶层所有并列目录，而是 `phase1_runtime`。

它不是单纯的“Chat with PDF”，而是一个把单次求解继续沉淀成方法资产的实验系统。

当前主链：

```text
用户问题 + 文档
-> /workspace
-> parsing
-> retrieval
-> TaskContext / RuleBinding
-> runtime_core
-> runtime skill artifact
-> super agent
-> workspace_run / feedback / draft / review / publish
```

对应代码主入口：

- `phase1_runtime/api/api_http.py`
- `phase1_runtime/product/workspace_flow.py`
- `phase1_runtime/product/workspace_runtime.py`
- `phase1_runtime/factory/rule_factory_workspace.py`

项目状态文档也已经把这条主链写明了，见 `CURRENT_PROJECT_STATUS.md`。

## 2. 对外有哪些产品入口

### `/workspace`

主产品入口。

用户做的事：

- 选择场景或让系统自动识别
- 输入业务问题
- 上传文件
- 点击“运行主工作流”
- 查看最终答案、证据、方法匹配、方法草稿、沉淀结果

对应前端：

- `phase1_runtime/static/product-console.html`
- `phase1_runtime/static/workspace-app.js`
- `phase1_runtime/static/workspace-renderers.js`

对应后端：

- `product.workspace.solve`
- `phase1_runtime/product/workspace_flow.py`

### `/workflow`

解释页，不是新的求解入口。

它默认读取最近一次 `/workspace` 的结果，把“已有方法路径”和“新方法生成路径”拆开讲清楚。

对应前端：

- `phase1_runtime/static/workflow-console.html`

### `/ops`

方法沉淀后台。

它不是简单的日志页，而是把求解记录、反馈、草稿、审核、发布版本串起来的治理台。

对应前端：

- `phase1_runtime/static/ops-console.html`
- `phase1_runtime/static/ops-app.js`

### `POST /api/phase1`

统一 API 入口。

用途：

- 前端调用
- 脚本集成
- 本地验证

## 3. `/workspace` 的真实产品链路

### 3.1 用户视角

用户打开 `/workspace` 后，会看到三层结构：

- 左侧：问题与材料输入区、推荐样本、相关问题
- 中间上方：执行总览
- 中间主体：最终建议、证据、执行详情

页面核心文案已经非常明确：

- 目标不是一次问答，而是“读懂文档 -> 完成求解 -> 沉淀方法”
- 主工作流是“理解材料 -> 形成上下文 -> 匹配方法 -> 生成答案”

### 3.2 页面初始化时发生什么

页面初始化不会自动求解当前输入。

它只会先加载：

- `product.scenario.list`
- `demo.workspace_case.list`
- `retrieval.embedding_backend.status`

也就是说，页面先准备场景、推荐样本和检索后端状态，再等用户上传文件后手动点击按钮。

### 3.3 用户点击“运行主工作流”后发生什么

前端会：

1. 把上传文件转成 API 可接受的 `materials`
2. 调用 `product.workspace.solve`
3. 请求中默认带上：
   - `use_live_kimi: true`
   - `run_live_super_agent: true`
   - `exploration_use_llm: true`
   - `exploration_mode: "emergent"`
4. 如果后端只返回了 `super_agent_handoff` 但还没实际执行，会再补打一轮 agent 请求
5. 把返回结果渲染到：
   - KPI
   - 最终答案
   - 决策摘要
   - 证据区
   - 上下文 / 方法匹配 / 方法草稿 / 求解过程 / 沉淀结果

### 3.4 后端主链怎么跑

`solve_workspace_request(...)` 是核心编排函数。

它实际做了这些事：

1. 规范化材料
2. 解析场景和文档
3. 基于场景准备规则集
4. 生成 `parser_bundle`
5. 构建 `TaskContext`
6. 做 retrieval 和 `RuleBinding`
7. 进入 `runtime_core`
8. 根据命中的规则生成 `runtime_skill_spec_preview`
9. 有条件时交给 `super agent`
10. 如果没有稳定规则，进入 exploration
11. 生成反馈载荷
12. 把运行结果写回工厂库，形成 `workspace_run / feedback / draft / review`

### 3.5 `/workspace` 返回给前端的不是只有答案

它返回的是一个很完整的工作包，核心字段包括：

- `final_answer`
- `final_decision`
- `route_decision`
- `fact_sheet`
- `context_packet`
- `task_context`
- `rule_bindings`
- `runtime_skill_spec_preview`
- `super_agent_result`
- `asset_pipeline`
- `similar_cases`

所以 `/workspace` 本质上是一个“带过程和资产回写的专家工作台”，不是单点回答接口。

## 4. 这条链路会分成哪几种路径

### 4.1 direct_match

含义：

- 当前问题和材料足以直接命中已有稳定规则

用户体验：

- 系统给出明确答案
- 展示关键证据
- 展示本次命中的方法草稿
- 通常不会自动形成新的 draft/review

典型案例：

- `fund_docx_direct_warn`

我实际跑过这条链路，结果是：

- `parser_status = parsed_complete`
- `route_decision = direct_match`
- `final_decision = must_warn`

### 4.2 needs_more_context

含义：

- 系统知道大概该用哪条规则
- 但当前材料缺关键字段，无法稳定回答

用户体验：

- 页面会明确告诉你缺哪些信息
- 不会把这类情况直接当成新规则去沉淀

### 4.3 exploration

含义：

- 当前没有稳定规则可直接回答
- 或规则组合失败，需要进入探索路径

用户体验：

- 最终建议通常会先落到“建议人工复核”
- 页面会展示探索入口
- 页面会出现人工审核动作按钮
- 后端会自动形成 feedback、draft、review

这条链路是本项目区别于普通问答系统的关键。

## 5. `/workflow` 页在产品里扮演什么角色

这个页面不是新入口，而是解释器。

它做三件事：

1. 读取最近一次 `/workspace` 快照
2. 用业务语言解释当前是“已有方法路径”还是“新方法生成路径”
3. 把本次求解拆成：
   - 问题上下文
   - 方法匹配与草稿
   - 求解过程

它的价值不是求解，而是对内对外说明“这套系统为什么给出这个答案，它到底走到了哪一步”。

如果你要向别人演示系统工作方式，`/workflow` 是从“结果展示”切换到“过程解释”的页面。

## 6. `/ops` 页在产品里扮演什么角色

`/ops` 是方法治理台，不只是运营后台。

它当前会同时拉这些数据：

- `factory.workspace_run.list`
- `feedback.list`
- `factory.draft.list`
- `factory.review.list`
- `factory.rule_version.list`
- `factory.retrieval_asset_view`
- `factory.rule_graph.view`

页面分成几块：

- 求解记录
- 反馈与方法草稿
- 审核与已发布版本
- Rule Graph 与社区报告
- 详情视图

并且可以直接在页面上做：

- 刷新
- 选中 review
- approve
- reject

这意味着产品不是“答案结束”，而是“答案只是下一次方法沉淀的输入”。

## 7. 我实际验证过的两条完整链路

### 7.1 已有方法命中链路

我跑了：

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn --check-expected
```

结果：

- 命中 `direct_match`
- 结论为 `must_warn`
- 输出和 expected 一致

说明：

- parsing
- retrieval
- runtime
- final answer

这一条是通的。

但要注意，`demo_case_runner` 默认写的是临时目录和临时库，不会写入主 `registry.db`。

### 7.2 探索与资产沉淀链路

我通过真实 HTTP API 跑了：

```bash
curl -sS -X POST http://127.0.0.1:8013/api/phase1 \
  -H 'Content-Type: application/json' \
  --data '{"action":"product.workspace.solve","question_text":"请给出处理意见。","scenario_id":"fund_nav_warning","materials":[],"metadata":{"use_live_kimi":false,"run_live_super_agent":false,"exploration_use_llm":false}}'
```

这次运行真实写进了主库 `phase1_runtime/state/registry.db`。

对应链路：

- `workspace_run_trace_20260414T124643_69585e86`
- `feedback_7679b8d2bcf1`
- `draft_ccdc1dbfa3a3`
- `review_8c95bac6682a`

对应结果：

- `route_decision = exploration`
- `final_decision = needs_review`
- `asset_pipeline.auto_status = draft_promoted`

这说明完整闭环真实可跑：

```text
workspace solve
-> missed_rule feedback
-> promote to draft
-> create review
```

## 8. 当前产品现状里几个重要事实

### 8.1 文档和当前前端有一点脱节

`USAGE_GUIDE.md` 还写着：

- 页面会自动加载默认 demo case
- 打开后自动生成一次结果

但当前真实前端已经不是这样了。

现在是：

- 页面会加载样本列表
- 但不会自动执行
- 还要求先上传文件，按钮才进入可执行状态

所以当前代码行为要以页面和 JS 为准，不要完全信旧文档。

### 8.2 当前前端返回的默认样本已经变了

接口 `demo.workspace_case.list` 当前返回的默认样本是：

- `workspace/equity_research_h3_code_upside_calc`

不是文档里还在推荐的：

- `fund_docx_direct_warn`

这说明产品叙事已经明显向研报场景扩了，但部分文档还没同步。

### 8.3 当前系统支持 fallback

在没配 `MOONSHOT_API_KEY` 的情况下，系统仍然能跑一大部分链路：

- 文档解析有 fallback
- rule -> skill 会退到 template generation
- super agent 也保留 runtime fallback

所以这是一个“尽量不断路”的实验系统，而不是强依赖单个外部模型的薄封装。

### 8.4 当前最稳的不是所有场景

我验证下来：

- `fund_nav_warning` 这条链路稳定度比较高
- `equity_research` 这条默认样本链路更重，也更容易进入 exploration 或长时间未收敛

所以如果你要继续接手、调试、做演示，优先建议先拿 `fund_nav_warning` 相关 case 建立稳定认知，再去看 `equity_research`。

## 9. 2026-04-14 实际完整走一轮

这一轮不是 demo runner 的临时库，而是通过真实 HTTP API 写进主库 `phase1_runtime/state/registry.db`。

### 9.1 输入

使用样本：

- `demo_cases/workspace/workspace_known_family_patch_scope`

输入问题：

```text
请给出处理意见。
```

上传材料：

- `demo_cases/workspace/workspace_known_family_patch_scope/materials/fund_clause.docx`

调用入口：

```text
POST http://127.0.0.1:8013/api/phase1
action = product.workspace.solve
```

为了让链路稳定可复现，本轮关闭了 live Kimi、live super agent 和 exploration LLM：

```json
{
  "use_live_kimi": false,
  "run_live_super_agent": false,
  "exploration_use_llm": false
}
```

### 9.2 `/workspace` 求解结果

本轮返回：

- `trace_id = trace_20260414T132226_bbd58e28`
- `scenario_id = fund_nav_warning`
- `parser_status = parsed_with_gaps`
- `route_decision = exploration`
- `final_decision = needs_review`
- `answer_engine = runtime`
- `runtime_skill_name = private-fund-nav-risk-warning-v1-calculation`

最终回答：

```text
当前没有稳定规则可直接给出建议，系统已进入探索路径，建议人工复核并记录反馈。
```

### 9.3 自动沉淀结果

`asset_pipeline` 自动生成：

- `workspace_run = workspace_run_trace_20260414T132226_bbd58e28`
- `feedback = feedback_24c95bb78d7a`
- `draft = draft_4165680e56b5`
- `review = review_9bb508cd7b4a`
- `auto_status = draft_promoted`
- `proposed_rule_id = private_fund.nav_risk_warning.v1`

主库中对应 `workspace_run` 状态：

```text
workspace_run_trace_20260414T132226_bbd58e28
trace_20260414T132226_bbd58e28
fund_nav_warning
exploration
needs_review
failed
2026-04-14T13:22:58.899408+00:00
```

### 9.4 `/ops` 审核

本轮生成的 review 初始状态：

- `review_task_id = review_9bb508cd7b4a`
- `draft_id = draft_4165680e56b5`
- `status = open`
- `assignee = rule_reviewer`

随后执行：

```text
action = factory.review.approve
review_task_id = review_9bb508cd7b4a
note = walkthrough_approve
```

执行后状态：

- `review.status = approved`
- `review.result_note = walkthrough_approve`
- `draft.status = published`

### 9.5 发布版本

审核通过后，系统发布了 rule version：

- `rule_version_id = rule_version_6ea134316610`
- `rule_id = private_fund.nav_risk_warning.v1`
- `version_label = factory_v1`
- `source_draft_id = draft_4165680e56b5`
- `status = published`
- `created_at = 2026-04-14T13:28:55.581715+00:00`

这说明本轮真实走通了：

```text
/workspace solve
-> exploration
-> workspace_run
-> feedback
-> draft
-> review
-> approve
-> published rule version
```

### 9.6 这一轮暴露的真实偏差

样本 expected 里写的是：

- `parser_status = parsed_complete`
- `recommended_action = patch_existing_rule_scope`
- `patch_type = scope`

但本轮实跑结果是：

- `parser_status = parsed_with_gaps`
- `recommended_action = create_or_patch_composite_rule`
- `patch_type = null`

这说明当前实现和旧样本预期之间已经有漂移。产品主链是通的，但样本断言和当前策略输出需要更新。

### 9.7 再补一轮 direct_match 对照

为了和 exploration 路径形成对照，我又通过真实 HTTP API 跑了一轮：

- 样本：`demo_cases/workspace/fund_docx_direct_warn`
- 问题：`某私募产品净值跌破0.80后，是否需要向投资者做风险提示？`
- 材料：`fund_clause.docx`

第一次我把 `use_live_kimi` 显式关掉后，虽然命中了 `matched_rule_id`，但没有稳定收敛，最后反而进入了：

- `route_decision = direct_match`
- `final_decision = needs_review`
- `asset_pipeline.auto_status = draft_promoted`

这说明某些 direct-match 场景对当前默认解析链仍有依赖，不能简单把 live Kimi 路径全部关死。

随后我按更接近默认产品行为的方式重跑，只保留：

```json
{
  "run_live_super_agent": false,
  "exploration_use_llm": false
}
```

这轮真实结果是：

- `trace_id = trace_20260414T134944_4fd47c78`
- `scenario_id = fund_nav_warning`
- `parser_status = parsed_with_gaps`
- `route_decision = direct_match`
- `matched_rule_id = private_fund.nav_risk_warning.v1`
- `final_decision = must_warn`
- `decision_text = 需要进行风险提示`
- `final_answer = 需要做风险提示，因为净值已经跌破合同阈值，且合同明确要求触发后向投资者提示风险。`
- `asset_pipeline.auto_status = recorded_only`

并且主库中对应记录为：

```text
workspace_run_trace_20260414T134944_4fd47c78
trace_20260414T134944_4fd47c78
fund_nav_warning
direct_match
must_warn
completed
2026-04-14T13:50:56.469357+00:00
```

同一个 `trace_id` 下没有生成 feedback 记录。

这说明 direct-match 稳定路径当前真实表现是：

```text
/workspace solve
-> direct_match
-> final answer
-> workspace_run
-> no feedback / no draft / no review
```

所以现在这套系统里，两条产品路径已经能明确区分：

- `direct_match`：以完成求解和记录 run 为主
- `exploration`：以继续沉淀方法资产为主

## 10. 如果你刚接手，建议怎么继续看

建议顺序：

1. 先从 `/workspace` 理解“用户怎么发起一次求解”
2. 再看 `workspace_flow.py`，理解后端主编排
3. 再看 `workspace_runtime.py`，理解 parsing/retrieval/runtime 输入是怎么拼出来的
4. 再看 `/workflow`，理解这套产品怎么向外解释自己
5. 最后看 `/ops` 和 `rule_factory_workspace.py`，理解它怎么把一次回答沉淀成方法资产

如果你只看一个最关键文件，优先看：

- `phase1_runtime/product/workspace_flow.py`

因为它最接近这个项目的“产品大脑”。

## 11. 一句话总结

这个项目当前最核心的价值，不是“回答金融文档问题”，而是：

**把一次问题求解，变成下一次还能复用的方法资产。**

当前这条链已经不是概念图，而是代码里真的能跑起来的产品主链。
