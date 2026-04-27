# 当前重构收口基线

目的：

- 记录这一轮拆分之后的**新边界**
- 为下一轮继续拆分提供稳定锚点
- 避免后续又把逻辑重新塞回“大文件”

原则：

- 不描述历史过程
- 只描述当前已经落地的边界
- 以代码为准

---

## 一、当前最重要的拆分结果

这一轮已经先对三个最重的热点做了第一刀，并继续把两个后端热点拆成独立模块：

1. [workspace_flow.py](/home/u2023312337/self_learning/phase1_runtime/product/workspace_flow.py)
2. [rule_factory_service.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_service.py)
3. [product-console.html](/home/u2023312337/self_learning/phase1_runtime/static/product-console.html)

目标不是彻底重构，而是先把“继续堆功能就会打结”的部分拆出基础边界。

---

## 二、前端基线

### 1. `/workspace`

当前已经拆成三层：

- [product-console.html](/home/u2023312337/self_learning/phase1_runtime/static/product-console.html)
  只保留页面结构
- [workspace-renderers.js](/home/u2023312337/self_learning/phase1_runtime/static/workspace-renderers.js)
  负责纯渲染逻辑
- [workspace-app.js](/home/u2023312337/self_learning/phase1_runtime/static/workspace-app.js)
  负责状态、请求、事件绑定、页面控制

**约束：**

- 不再把大段模板字符串渲染逻辑塞回 `product-console.html`
- 新的渲染 helper 优先放进 `workspace-renderers.js`
- 新的状态或交互优先放进 `workspace-app.js`

### 2. `/ops`

当前已经拆成三层：

- [ops-console.html](/home/u2023312337/self_learning/phase1_runtime/static/ops-console.html)
  只保留页面结构
- [ops-renderers.js](/home/u2023312337/self_learning/phase1_runtime/static/ops-renderers.js)
  负责卡片和详情渲染
- [ops-app.js](/home/u2023312337/self_learning/phase1_runtime/static/ops-app.js)
  负责拉取数据、绑定按钮、刷新列表、审核动作

**约束：**

- 不再把详情卡渲染直接写回 `ops-console.html`
- 新的 UI 呈现优先放 `ops-renderers.js`
- 新的交互逻辑优先放 `ops-app.js`

### 3. 当前静态文件布局

当前静态目录：

- [app-core.js](/home/u2023312337/self_learning/phase1_runtime/static/app-core.js)
- [app-shell.css](/home/u2023312337/self_learning/phase1_runtime/static/app-shell.css)
- [product-console.html](/home/u2023312337/self_learning/phase1_runtime/static/product-console.html)
- [workspace-renderers.js](/home/u2023312337/self_learning/phase1_runtime/static/workspace-renderers.js)
- [workspace-app.js](/home/u2023312337/self_learning/phase1_runtime/static/workspace-app.js)
- [workflow-console.html](/home/u2023312337/self_learning/phase1_runtime/static/workflow-console.html)
- [prototype-console.html](/home/u2023312337/self_learning/phase1_runtime/static/prototype-console.html)
- [ops-console.html](/home/u2023312337/self_learning/phase1_runtime/static/ops-console.html)
- [ops-renderers.js](/home/u2023312337/self_learning/phase1_runtime/static/ops-renderers.js)
- [ops-app.js](/home/u2023312337/self_learning/phase1_runtime/static/ops-app.js)
- [registry-console.html](/home/u2023312337/self_learning/phase1_runtime/static/registry-console.html)

---

## 三、后端基线

### 1. `workspace_flow.py`

当前边界已经变成三层：

- [workspace_flow.py](/home/u2023312337/self_learning/phase1_runtime/product/workspace_flow.py)
  负责 solve 主链编排和最终结果汇总
- [workspace_runtime.py](/home/u2023312337/self_learning/phase1_runtime/product/workspace_runtime.py)
  负责场景解析、规则准备、runtime 输入构建、runtime 执行
- [workspace_support.py](/home/u2023312337/self_learning/phase1_runtime/product/workspace_support.py)
  负责展示 payload、super-agent 资产准备、exploration 选择、feedback payload 组装

当前 `workspace_flow.py` 主要保留：

- `solve_workspace_request`

当前 `workspace_runtime.py` 承担：

- `_scenario_seed_bundle`
- `_scenario_rule_ids`
- `_resolve_workspace_scenario_and_parse`
- `_prepare_workspace_rules`
- `_build_workspace_runtime_inputs`
- `_run_workspace_runtime`
- `_make_shortcut_runtime_result`

当前 `workspace_support.py` 承担：

- rule binding 展示与解释
- solution view 组装
- super-agent handoff / result 收敛
- exploration backend 选择
- feedback defaults / feedback payload 组装

这意味着 `solve_workspace_request()` 已经更接近真正的 orchestrator，而不是大杂烩函数。

**约束：**

- `solve_workspace_request()` 继续只做主链编排
- 新的 payload 组装逻辑不要直接堆回主函数
- 新的 backend 切换逻辑不要直接再塞回主函数

### 2. `rule_factory_service.py`

当前边界已经变成两层：

- [rule_factory_service.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_service.py)
  负责 case / draft / version / rollback 等非 review 主线
- [rule_factory_review_flow.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_review_flow.py)
  负责 create review / approve / reject / rerun / preview execution

当前 review flow 模块已承接：

- `_preview_draft_execution`
- `_build_review_payload`
- `_prepare_publish_version`
- `_approve_review_and_publish`
- `_rerun_rejected_exploration`
- `_reject_review_and_maybe_rerun`
- `create_review_for_draft`
- `approve_review`
- `reject_review`

另外已经补齐的闭环能力：

- reject review -> rerun multi-agent exploration -> new feedback -> new draft -> new review
- review 前 `test_execution_preview`
- `test_execution_preview` 已进一步扩展为：
  - `runtime_preview`
  - `method_draft_preview`
  - `agent_preview`

**约束：**

- `create_review_for_draft()` 继续只负责 review 创建主流程
- `approve_review()` 继续只负责审批主流程
- 复杂 payload 组装必须留在 helper

### 3. `rule_factory_feedback.py`

当前边界已经变成两层：

- [rule_factory_feedback.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_feedback.py)
  负责 feedback 记录、分类、promotion 入口
- [rule_factory_draft_builder.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_draft_builder.py)
  负责 template rule 选择、draft target 决策、draft payload 组装、existing draft 复用判断

当前 `rule_factory_feedback.py` 主要保留：

- `feedback_semantics`
- `_apply_explicit_recommended_action`
- `_recommended_action_from_source_payload`
- `draft_action_from_feedback`
- `record_feedback`
- `classify_feedback`
- `promote_feedback_to_draft`

当前 `rule_factory_draft_builder.py` 承担：

- `_resolve_source_dataset_id`
- `_runtime_metadata_from_feedback`
- `_template_rule_for_feedback`
- `_resolve_draft_target`
- `_base_draft_payload`
- `_attach_patch_target`
- `_attach_composition_payload`
- `build_draft_payload_from_feedback`
- `existing_draft_for_feedback`

这意味着 feedback 模块本身不再同时承担“分类策略”和“完整 draft 构建”两种职责。

---

## 四、行为基线

### 1. 探索后端默认值

当前默认 exploration backend 已切到：

- `multi_agent_exploration`

保留回退逻辑：

- 失败时自动回退到内置 `run_exploration_runtime`

### 2. 预览与审核闭环

当前已经具备：

- exploration -> feedback -> draft -> auto review
- review payload 带 `test_execution_preview`
- reject -> auto rerun exploration -> new feedback -> new draft -> new review

### 3. 前端展示基线

当前页面已统一到“方法/解法”叙事：

- 问题求解
- 解法形成
- 能力演示
- 方法沉淀
- 记录

同时：

- 直接整块 JSON 的展示已基本清理
- 详情区以摘要卡为主

---

## 五、已跑过的关键检查

这轮重构后，至少跑过以下关键检查：

- `python3 -m py_compile phase1_runtime/factory/rule_factory_service.py phase1_runtime/factory/rule_factory_review_flow.py phase1_runtime/factory/rule_factory_workspace.py phase1_runtime/tests/test_rule_factory.py`
- `python3 -m py_compile phase1_runtime/factory/rule_factory_feedback.py phase1_runtime/factory/rule_factory_draft_builder.py`
- `python3 -m py_compile phase1_runtime/product/workspace_flow.py phase1_runtime/product/workspace_runtime.py`
- `python3 -m py_compile phase1_runtime/product/workspace_flow.py phase1_runtime/product/workspace_support.py`
- `node --check phase1_runtime/static/workspace-renderers.js`
- `node --check phase1_runtime/static/workspace-app.js`
- `node --check phase1_runtime/static/ops-renderers.js`
- `node --check phase1_runtime/static/ops-app.js`
- `python3 -m unittest phase1_runtime.tests.test_product_service.Phase1ProductServiceTests.test_workspace_run_auto_promotes_exploration_to_draft`
- `python3 -m unittest phase1_runtime.tests.test_product_service.Phase1ProductServiceTests.test_workspace_auto_routes_equity_research_scenario`
- `python3 -m unittest phase1_runtime.tests.test_product_service.Phase1ProductServiceTests.test_workspace_final_answer_prefers_super_agent_when_available`
- `python3 -m unittest phase1_runtime.tests.test_product_service.Phase1ProductServiceTests.test_workspace_exploration_defaults_to_multi_agent_backend_when_available`
- `python3 -m unittest phase1_runtime.tests.test_product_service.Phase1ProductServiceTests.test_workspace_exploration_falls_back_to_builtin_when_external_backend_errors`
- `python3 -m unittest phase1_runtime.tests.test_rule_factory.Phase1RuleFactoryTests.test_reject_review_reruns_multi_agent_exploration_and_opens_new_review`
- `python3 -m unittest phase1_runtime.tests.test_rule_factory.Phase1RuleFactoryTests.test_approve_rejected_review_fails_publish_gate`
- `python3 -m unittest phase1_runtime.tests.test_rule_factory.Phase1RuleFactoryTests.test_promote_feedback_to_draft`
- `python3 -m unittest phase1_runtime.tests.test_rule_factory.Phase1RuleFactoryTests.test_create_review_for_draft_includes_three_layer_execution_preview`

---

## 六、下一步建议拆分顺序

在当前基线上，推荐的下一步拆分顺序：

1. [workspace_flow.py](/home/u2023312337/self_learning/phase1_runtime/product/workspace_flow.py)
   再判断是否把 parse/runtime input 构建提成独立模块
2. [rule_factory_review_flow.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_review_flow.py)
   再判断是否把 preview execution 和 publish approval 继续拆开
3. [workflow-console.html](/home/u2023312337/self_learning/phase1_runtime/static/workflow-console.html)
   如果再回前端，再拆成 `workflow-renderers.js` + `workflow-app.js`
4. [registry-console.html](/home/u2023312337/self_learning/phase1_runtime/static/registry-console.html)
   按同样方式拆分

---

## 七、当前不要做的事

在继续拆分前，当前不建议：

- 再改一轮大口径命名
- 再引入新的后端能力分支
- 把已经抽出的 helper 再塞回大文件
- 在没有测试保护的情况下做跨层大搬家

一句话：

**现在最重要的是沿着已形成的边界继续拆，而不是重新发明新的边界。**
