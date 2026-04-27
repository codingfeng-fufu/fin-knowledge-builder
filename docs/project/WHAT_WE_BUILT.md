# 我们到底做了什么

> 这是一份面向第一次接手项目的人写的系统说明。
> 目标不是讲历史，而是让人快速看懂：这个系统现在能做什么、怎么跑、主流程怎么走、各部分代码在哪里。

---

## 1. 一句话定义

我们现在做出来的，不是一个简单的 `Chat with PDF` 工具。

它是一个**从文档理解出发，完成问题求解，并把求解过程继续沉淀为可复用方法的实验系统**。

可以把它理解成一个完整闭环：

```text
文档 / 问题
-> 理解文档
-> 匹配已有方法
-> 执行求解
-> 生成答案
-> 记录结果
-> 沉淀反馈 / 草稿 / 审核 / 发布
-> 进入下一轮复用
```

---

## 2. 这个系统对外有哪些入口

当前所有入口都由同一个 Python HTTP 服务提供：

- `/workspace`
  问题求解主入口
- `/workflow`
  展示一次求解是如何形成的
- `/prototype`
  演示原型能力和 demo case
- `/ops`
  方法沉淀与审核运营入口
- `/console`
  记录中心
- `POST /api/phase1`
  统一 API 入口
- `/health`
  健康检查

HTTP 服务入口在：

- `phase1_runtime/api/api_http.py`

统一 API 分发在：

- `phase1_runtime/api/api_dispatch.py`

---

## 3. 这个系统现在已经具备哪些能力

### 3.1 文档与问题理解

系统可以接收：

- 纯文本材料
- `docx`
- `pdf`
- 多材料组合

它会做：

- 上传材料标准化
- 基础解析
- 场景识别
- 文档类型识别
- query-aware context 构建
- fact sheet 生成

主要代码：

- `phase1_runtime/product/workspace_runtime.py`
- `phase1_runtime/parsing/`

---

### 3.2 方法匹配与 runtime 执行

系统不会直接把问题扔给一个大模型。

它会先走一条结构化主链：

- 根据场景加载规则/方法
- 做 retrieval
- 构建 `TaskContext`
- 计算 `RuleBinding`
- 进入 runtime 执行
- 决定是：
  - `direct_match`
  - `rule_composable`
  - `needs_more_context`
  - `exploration`

主要代码：

- `phase1_runtime/product/workspace_runtime.py`
- `phase1_runtime/retrieval/`
- `phase1_runtime/runtime_core/`

---

### 3.3 运行期 skill 产物与 super agent

如果 runtime 命中了可执行方法，系统会把规则编译成运行期 skill artifact，然后把问题交给 super agent。

当前具备：

- `rule -> runtime skill artifact`
- `skill -> super agent handoff`
- `super agent -> 最终答案`

当前 super agent 有两种 backend：

- `builtin`
  当前默认
- `mini_coding_agent`
  可选，适合代码/执行类任务，不是默认

主要代码：

- `phase1_runtime/skills/`
- `phase1_runtime/agents/super_agent_service.py`
- `phase1_runtime/agents/mini_coding_agent_adapter.py`

---

### 3.4 无现成方法时的多智能体探索

当没有稳定方法可直接回答，或者组合失败时，系统会进入 exploration。

当前默认 exploration backend 已经是外部多智能体探索系统：

- `muti_agent_exploration`

并保留回退：

- 如果外部探索失败，自动退回内置 `builtin exploration`

主要代码：

- `phase1_runtime/analysis/multi_agent_exploration_adapter.py`
- `phase1_runtime/analysis/external_rule_discovery_runner.py`
- `phase1_runtime/analysis/exploration_runtime.py`

---

### 3.5 方法沉淀与审核闭环

系统不是只回答一次就结束。

当前已经具备完整的沉淀链：

```text
workspace run
-> feedback
-> draft
-> review
-> approve / reject
-> publish / rerun exploration
```

而且 reject 不是终点。

当前 reject 已经会自动：

- rerun 多智能体探索
- 生成新的 feedback
- promote 成新的 draft
- 自动再创建新的 review

也就是：

```text
探索
-> 草稿
-> 审核
-> 驳回
-> 自动重跑探索
-> 新草稿
-> 新审核
```

主要代码：

- `phase1_runtime/factory/rule_factory_workspace.py`
- `phase1_runtime/factory/rule_factory_feedback.py`
- `phase1_runtime/factory/rule_factory_draft_builder.py`
- `phase1_runtime/factory/rule_factory_review_flow.py`
- `phase1_runtime/factory/rule_factory_service.py`

---

### 3.6 数据集、回放、记录、注册中心

系统不只有在线求解入口，还支持：

- dataset 导入
- dataset 校验
- dataset 回放 / rerun
- workflow run / run_sync
- registered dataset / workflow 记录
- workspace run 记录
- case / draft / review / version / rollback 查询

主要代码：

- `phase1_runtime/datasets/`
- `phase1_runtime/registry/`
- `phase1_runtime/factory/`

---

## 4. 页面分别在看什么

### 4.1 `/workspace` 问题求解

这是主入口。

用户在这里：

- 提问题
- 上传文档
- 手动点击执行
- 看最终答案
- 看上下文、方法匹配、求解记录、沉淀结果

对应页面：

- `phase1_runtime/static/product-console.html`
- `phase1_runtime/static/workspace-app.js`
- `phase1_runtime/static/workspace-renderers.js`

---

### 4.2 `/workflow` 解法形成

这个页面更偏“为什么这样解”。

主要看：

- 上下文是怎么形成的
- 方法匹配结果
- 方法草稿
- 求解过程

对应页面：

- `phase1_runtime/static/workflow-console.html`

---

### 4.3 `/prototype` 能力演示

这个页面更像 demo / show case。

主要看：

- demo case 列表
- 原型 flow
- 样本运行结果

对应页面：

- `phase1_runtime/static/prototype-console.html`
- `phase1_runtime/prototype/`

---

### 4.4 `/ops` 方法沉淀

这个页面是运营和审核后台。

主要看：

- workspace run
- feedback
- rule draft
- review
- published version
- rollback

而且现在 review 里已经能看到：

- `runtime_preview`
- `method_draft_preview`
- `agent_preview`
- reject 后的自动 rerun 结果

对应页面：

- `phase1_runtime/static/ops-console.html`
- `phase1_runtime/static/ops-app.js`
- `phase1_runtime/static/ops-renderers.js`

---

### 4.5 `/console` 记录中心

这里主要看：

- dataset
- workflow run
- 历史记录

对应页面：

- `phase1_runtime/static/registry-console.html`

---

## 5. 主流程到底怎么跑

当前最重要的主流程是：

- `product.workspace.solve`
- 即 `solve_workspace_request(...)`

主入口：

- `phase1_runtime/product/workspace_flow.py`

### 5.1 工作流主干

当前主干可以概括成：

```text
输入问题 + 材料
-> normalize materials
-> 推断场景
-> 解析材料
-> 加载场景方法
-> 构建 parser bundle / context / fact sheet
-> retrieval
-> rule binding
-> runtime
-> skill artifact
-> super agent
-> exploration（必要时）
-> solution view / orchestration view
-> record workspace run
-> auto feedback / draft / review
-> 返回前端
```

### 5.2 现在代码里的分层

当前 `workspace` 主链已经被拆成三层：

- `phase1_runtime/product/workspace_flow.py`
  主编排器
- `phase1_runtime/product/workspace_runtime.py`
  场景解析、规则准备、runtime 输入构建、runtime 执行
- `phase1_runtime/product/workspace_support.py`
  展示视图、super agent、exploration、feedback payload

这三层的分工已经比较清楚：

- `workspace_flow`
  负责顺序调度
- `workspace_runtime`
  负责“怎么把问题和文档喂进 runtime”
- `workspace_support`
  负责“runtime 之后怎么变成用户可见结果和后续沉淀材料”

---

## 6. 审核与沉淀主流程怎么跑

这是系统第二重要的闭环。

### 6.1 从 workspace run 到 draft

当 `workspace` 路径产生了需要沉淀的反馈，系统会：

- 记录 `workspace_run`
- 记录 `feedback`
- 自动 `promote_feedback_to_draft`
- 自动 `create_review_for_draft`

主要代码：

- `phase1_runtime/factory/rule_factory_workspace.py`
- `phase1_runtime/factory/rule_factory_feedback.py`
- `phase1_runtime/factory/rule_factory_draft_builder.py`
- `phase1_runtime/factory/rule_factory_review_flow.py`

### 6.2 review 前会先做什么

review 不是一张空表。

当前 review payload 会自动带一份 `test_execution_preview`，包括：

- `runtime_preview`
- `method_draft_preview`
- `agent_preview`

也就是说，候选方法在进入人工审核前，已经会先经过一轮轻量试跑。

### 6.3 review 通过

通过后会：

- 校验可发布性
- 生成 published rule payload
- insert rule version
- insert case_rule_link

### 6.4 review 驳回

驳回后会：

- 标记 review rejected
- 标记 draft rejected
- 如果来源于外部 exploration
  - rerun exploration
  - record 新 feedback
  - promote 新 draft
  - 自动开新 review

### 6.5 当前工厂层分层

现在 factory 也已经拆层：

- `phase1_runtime/factory/rule_factory_service.py`
  case / draft / version / rollback 等通用 service
- `phase1_runtime/factory/rule_factory_review_flow.py`
  review / approve / reject / rerun / preview execution
- `phase1_runtime/factory/rule_factory_feedback.py`
  feedback 记录与分类、promotion 入口
- `phase1_runtime/factory/rule_factory_draft_builder.py`
  feedback -> draft payload 构建
- `phase1_runtime/factory/rule_factory_workspace.py`
  workspace run 侧的沉淀入口

---

## 7. API 现在支持什么

统一入口：

- `POST /api/phase1`

分发在：

- `phase1_runtime/api/api_dispatch.py`

当前主要 action 家族有：

### 7.1 产品求解

- `product.scenario.list`
- `product.solve.preview`
- `product.workspace.contract`
- `product.workspace.solve`

### 7.2 super agent

- `super_agent.run`

### 7.3 prototype / demo

- `prototype.flow.list`
- `prototype.flow.run`
- `demo.workspace_case.list`
- `demo.workspace_case.get`

### 7.4 dataset / workflow

- `dataset.validate`
- `dataset.import`
- `dataset.summary`
- `dataset.replay`
- `dataset.rerun`
- `workflow.full`

### 7.5 registry

- `registry.dataset.register`
- `registry.dataset.list`
- `registry.dataset.get`
- `registry.workflow.run`
- `registry.workflow.run_sync`
- `registry.workflow.list`
- `registry.workflow.get`

### 7.6 factory / 沉淀后台

- `factory.case.ingest`
- `factory.case.list`
- `factory.case.get`
- `factory.draft.generate`
- `factory.draft.list`
- `factory.draft.get`
- `factory.review.create`
- `factory.review.list`
- `factory.review.get`
- `factory.review.approve`
- `factory.review.reject`
- `factory.rule_version.list`
- `factory.rule_version.get`
- `factory.rule_version.rollback`
- `factory.case_rule_link.list`
- `factory.rollback.list`
- `factory.workspace_run.list`
- `factory.workspace_run.get`
- `factory.feedback.promote_to_draft`
- `factory.retrieval_asset_view`

### 7.7 feedback / retrieval status

- `feedback.record`
- `feedback.list`
- `feedback.get`
- `retrieval.embedding_backend.status`

---

## 8. 这个系统内部到底有哪些包

按职责看，核心包可以这样理解：

### `phase1_runtime/api`

负责：

- HTTP 服务
- API 请求解析
- action dispatch

### `phase1_runtime/product`

负责：

- `/workspace` 主链
- 产品场景 catalog
- 求解编排

### `phase1_runtime/parsing`

负责：

- 上传材料解析
- PDF / DOCX / 文本解析
- parser bundle
- query-aware context

### `phase1_runtime/retrieval`

负责：

- rule candidate retrieval
- similar case retrieval
- embedding backend 状态

### `phase1_runtime/runtime_core`

负责：

- runtime 执行
- route decision
- task context
- rule binding

### `phase1_runtime/skills`

负责：

- rule -> runtime skill artifact
- skill materialization
- artifact validation

### `phase1_runtime/agents`

负责：

- builtin super agent
- mini_coding_agent 适配
- tool 集合

### `phase1_runtime/analysis`

负责：

- exploration runtime
- 多智能体探索适配
- orchestration view

### `phase1_runtime/factory`

负责：

- feedback
- draft
- review
- publish
- rollback
- workspace run 沉淀

### `phase1_runtime/prototype`

负责：

- prototype flow
- demo case

### `phase1_runtime/datasets`

负责：

- dataset import / replay / rerun

### `phase1_runtime/registry`

负责：

- dataset registry
- workflow run registry

---

## 9. 外部系统已经接了哪些

### 9.1 `muti_agent_exploration`

作用：

- 作为默认 exploration backend

接入方式：

- 当前不是单独起 Flask 服务
- 而是通过 adapter + runner 脚本在主系统里调用

主要代码：

- `phase1_runtime/analysis/multi_agent_exploration_adapter.py`
- `phase1_runtime/analysis/external_rule_discovery_runner.py`

当前状态：

- 已接入
- 已是默认 exploration backend
- 失败会自动回退 builtin exploration

### 9.2 `mini_coding_agent`

作用：

- 作为可选 super agent backend
- 适合代码/执行类问题

主要代码：

- `phase1_runtime/agents/mini_coding_agent_adapter.py`
- `phase1_runtime/agents/super_agent_service.py`

当前状态：

- 已接入
- 不是默认 backend
- 当前默认仍是 builtin super agent

---

## 10. 当前默认行为

### 10.1 workspace 默认行为

- 进入 `/workspace` 不自动运行
- 必须手动上传并点击执行
- 如果没给 `scenario_id`，系统会自动识别场景

### 10.2 exploration 默认行为

- 默认优先走 `multi_agent_exploration`
- 外部失败自动回退 builtin exploration

### 10.3 super agent 默认行为

- 默认走 builtin super agent
- `mini_coding_agent` 只在显式切 backend 时用

### 10.4 审核默认行为

- `workspace` 跑出可沉淀反馈后，会自动：
  - feedback
  - draft
  - review

### 10.5 当前服务形态

- 单体 Python HTTP 服务
- 同时提供页面和 API
- 默认启动命令：

```bash
python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8010
```

---

## 11. 当前还没有做到的事

这份文档要诚实，所以也明确当前边界。

### 11.1 还没有文档级缓存 / 记忆复用

同一份材料重复上传时，仍会重新走解析链。

### 11.2 rule retrieval 还不是完整 rule-RAG

当前仍然是 hybrid retrieval，不是纯粹基于 query + evidence 的 rule-RAG。

### 11.3 `mini_coding_agent` 还不是默认执行层

它已经能接，但目前是可选，不是默认。

### 11.4 这还是实验系统

它已经可跑、可演示、可沉淀，但还不是生产多租户平台。

---

## 12. 现在最该怎么理解这个系统

最简单的理解方式是：

这个系统不是为了“答对一个问题”而存在。

它是为了把一次次问题求解，变成下一次还能继续复用的方法。

所以它同时做三件事：

1. 读懂文档和问题
2. 基于已有方法完成求解
3. 当现有方法不够时，探索、生成、审核、沉淀新的方法

如果用一句最适合对外讲的话来总结：

**我们不是在做一个文档问答工具，而是在做一个把答案逐步变成方法的系统。**

---

## 13. 推荐阅读顺序

如果是第一次接手，推荐按这个顺序看：

1. `WHAT_WE_BUILT.md`
2. `CURRENT_PROJECT_STATUS.md`
3. `REFACTOR_BASELINE.md`
4. `phase1_runtime/README.md`
5. `phase1_runtime/api/api_dispatch.py`
6. `phase1_runtime/product/workspace_flow.py`
7. `phase1_runtime/product/workspace_runtime.py`
8. `phase1_runtime/product/workspace_support.py`
9. `phase1_runtime/factory/rule_factory_review_flow.py`
10. `TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md`

