# System Feature Chain

## Scope

这份文档描述 `phase1_runtime` **当前已经落地的功能链**，重点回答：

1. 这个系统现在有哪些能力。
2. 这些能力在主链上如何串起来。
3. API、页面、方法沉淀和数据回放分别处于哪一段。

这不是目标态愿景文档，也不是代码分层文档。
如果你要看目录分层，看 `LAYER_MAP.md`。
如果你要看包职责，看 `SYSTEM_OVERVIEW.md`。
如果你要看接口字段和 payload，看 `API_CONTRACT.md`。

## One-Sentence Summary

`phase1_runtime` 是一个“把答案变成方法”的金融规则资产实验平台：
用户提交问题和文档后，系统先理解材料，再匹配或组合已有方法完成求解；如果现有方法不够，就进入探索与补救；最后把这次过程沉淀成可复用的方法资产。

## Terminology

为避免“规则”“方法”“资产”三个词混用，这里统一约定：

- `方法`：面向业务表达的说法，用户界面和产品叙述更常用。
- `规则`：运行时实际执行的结构化对象，代码里常见 `rule / rule_version / rule_binding`。
- `资产`：方法进入生命周期管理后的视角，强调 draft、review、publish、rollback、retrieval asset。

在当前系统里，这三个词在很多场景下描述的是同一类东西，只是视角不同。

## Current End-to-End Chain

当前稳定主链可以概括为：

```text
question + materials
-> /workspace
-> parsing
-> retrieval
-> TaskContext / RuleBinding
-> runtime_core
-> runtime skill artifact
-> super agent
-> trace / workspace_run / feedback / draft / review / publish
```

如果把它翻译成功能语言，就是：

```text
用户提问并上传文档
-> 系统读懂材料并组织证据
-> 系统匹配已有方法或组合多个方法
-> 系统产出最终建议
-> 系统把这次解法和证据沉淀为后续可复用的方法资产
```

## User-Facing Surfaces

当前对用户暴露的主要入口有 4 个：

| Surface | Role | Main Use |
| --- | --- | --- |
| `/workspace` | 主工作台 | 问题求解、文档上传、最终建议、方法沉淀入口 |
| `/prototype` | 原型演示入口 | 预设 flow 和 demo case 演示 |
| `/ops` | 方法运营后台 | workspace run、feedback、draft、review、publish、rollback |
| `POST /api/phase1` | 统一 API 入口 | 所有函数式能力的 HTTP 入口 |

另有一个基础可用性接口：

| Surface | Role |
| --- | --- |
| `GET /health` | 健康检查 |

## Functional Chains

### 1. Entry And Request Chain

这是系统接收请求、把前端和 API 串起来的入口链。

当前能力包括：

- 提供统一 HTTP 服务，同时承载页面和 API。
- 提供函数式 API 封装，允许直接用 payload 触发系统动作。
- 提供 `/workspace`、`/prototype`、`/ops`、`/console` 等页面入口。
- 提供统一的响应 envelope，包含 `ok / action / request_id / timestamp / data / error`。
- 提供 `GET /health` 健康检查。
- 提供 `POST /api/phase1`，把所有系统动作统一收口到一个 endpoint。

这一段对应的典型动作包括：

- `product.scenario.list`
- `product.solve.preview`
- `product.workspace.contract`
- `product.workspace.solve`
- `prototype.flow.list`
- `prototype.flow.run`
- `retrieval.embedding_backend.status`

### 2. Problem Understanding Chain

这是系统把“原始问题 + 原始文档”转成“可执行上下文”的链路。

当前能力包括：

- 接收 `question_text` 和 `materials`。
- 支持文本和真实二进制材料上传。
- 支持的当前主要文件类型包括：
  `txt`、`md`、`json`、`csv`、`log`、`html`、`htm`、`pdf`、`docx`、`xlsx`。
- 根据问题和材料自动识别场景，或接受手动指定场景。
- 对 PDF、DOCX、XLSX、HTML 等材料做统一文本层抽取。
- 构建文档预览和结构化问题包，供后续 retrieval 和 runtime 使用。

这一段的核心输出不是最终答案，而是 4 类中间产物：

1. `document_set`
   当前文档预览集合，供页面展示、trace 和记忆桥接使用。
2. `question_packet`
   对问题进行结构化，输出 `question_types / intents / document_types / extracted_inputs / scenario_hint / target_object`。
3. `fact_sheet`
   当前是 signal-based fact sheet，表示“哪些必需事实已经在材料中被 grounded”，而不是最终值级 facts。
4. `evidence_packets`
   当前可直接挂到答案、trace 和页面上的证据片段。

补充产物还包括：

- `document_chunks`
- `missing_fact_keys`
- `document_packet_preview`
- `question_packet_preview`

### 3. Scenario And Seed Capability Chain

这条链负责把系统的主入口和当前内置业务场景连接起来。

当前能力包括：

- 内置 3 个主场景：
  `fund_nav_warning`、`credit_notice`、`equity_research`。
- 每个场景自带默认问题、示例文档和规则种子。
- 支持自动根据关键词和材料内容推断更可能的场景。
- 支持基于内置场景快速做 preview，不需要用户先上传真实材料。

这条链的价值是：

- 让 `/workspace` 不只是一个空白输入框。
- 让系统具备默认问题模板、样本材料和规则 seed bundle。
- 让演示、回归和真实输入都能共用同一条主链。

### 4. Retrieval And Method Matching Chain

这是系统第一次接触“方法库”的地方。

当前能力包括：

- 根据 `question_packet`、`fact_sheet` 和证据做候选规则召回。
- 结合 lexical、semantic、signal hits、required fact hits 等信号做候选排序。
- 使用 embedding backend 做相似度支持。
- 返回当前 active embedding backend 以及所有可用 backend 状态。
- 构建 `TaskContext`，把问题、文档、证据和未解决槽位统一纳入同一上下文。
- 构建 `RuleBinding`，把候选规则和当前上下文绑定起来，为 runtime 提供可执行绑定。
- 查询历史 `workspace_run`，寻找相似案例。
- 在没有上传新材料且历史相似案例足够高置信时，允许走 shortcut case。

这一段的关键结果包括：

- `candidate_rules`
- `task_context`
- `rule_bindings`
- `similar_cases`
- `shortcut_case`
- `embedding_backend`

### 5. Runtime Execution Chain

这是系统的核心判定链，负责把候选方法真正执行起来。

当前能力包括：

- 构建运行时 trace。
- 编译路由决策。
- 自动补齐 rule 所需输入。
- 执行 tool step 和 llm step。
- 运行 validator。
- 记录 step contract、step result 和 final result。

当前 runtime 只会落到 4 种主路径：

1. `direct_match`
   命中稳定规则，直接执行。
2. `rule_composable`
   没有整题规则，但可由多个 atomic rule 组合完成求解。
3. `needs_more_context`
   已识别到相关方法，但材料缺关键字段。
4. `exploration`
   当前没有稳定方法可直接解决，进入探索路径。

在 `rule_composable` 路径下，系统还具备：

- 组合计划生成。
- 组合 DAG 执行。
- 把上一步 rule 输出注入下一步输入池。
- 输出 `composition_pattern / source_rule_ids / composition_plan`。

这条链还受一个全局总开关影响：

- `DISABLE_ALL_RUNTIME_RULES = False`

它控制的是“整个运行时方法库是否启用”，不是单条规则的单独布尔开关。

### 6. Final Answer Chain

runtime 给出结构化求解结果后，系统还要把结果变成最终可交付回答。

当前能力包括：

- 把 runtime 结果整理为最终 `final_decision` 和 `final_answer`。
- 根据当前命中的 rule binding 和 task context 生成 `runtime_skill_spec_preview`。
- 物化 `runtime skill artifact`。
- 为 `super_agent` 构建 handoff payload。
- 允许最终回答走 runtime fallback 或 super agent。
- super agent 优先消费 query-aware context packet，而不是盲目重新读全量文件。
- 输出面向前端的 `solution_view`。
- 输出面向解释的 `orchestration_view`。

最终这条链会向前端暴露：

- 最终建议
- 决策文本
- 路由类型
- 回答引擎
- 关键证据
- 执行详情
- 方法草稿
- 沉淀结果

### 7. Exploration And Gap Recovery Chain

当主 runtime 无法稳定完成求解时，系统不会直接失败，而是进入探索补救链。

当前能力包括：

- 生成 `case_draft`。
- 生成 `candidate_rule_drafts`。
- 生成 `evidence_pattern_suggestions`。
- 生成 `validator_pattern_suggestions`。
- 给出 `recommended_feedback_type`。
- 给出 `recommended_rule_ids`。
- 对缺少材料的情况，明确输出缺失事实键和值得补充的文档方向。

探索链当前有两种形态：

1. `controlled_deterministic_mvp`
   主系统内置的受控探索。
2. `multi_agent_exploration_*`
   调用外部 `muti_agent_exploration` 项目完成更强的发现型探索，再把结果映射回主系统。

这条链的目标不是立即“发布新方法”，而是把问题从“无解”转成“有候选方案、可追踪证据、可继续沉淀”的状态。

### 8. Method Accumulation Chain

这是系统和普通问答系统最不一样的一条链。

当前能力包括：

- 记录 `trace`。
- 记录 `workspace_run`。
- 记录 `feedback`。
- 自动根据 route 决策分类 feedback。
- 在合适情况下把 feedback 提升为 candidate rule draft。
- 生成或维护 case、draft、review、rule version、rollback、retrieval asset view。

这一条链的具体生命周期是：

```text
workspace solve
-> trace
-> workspace_run
-> feedback
-> candidate draft
-> review
-> publish
-> retrieval asset
-> later runtime reuse
```

当前已经落地的动作包括：

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

这条链同时定义了“单条方法是否生效”的当前逻辑：

- draft 不生效。
- under review 不生效。
- `published` 才会进入运行时可用方法池。
- `rolled_back` 会退出运行时可用方法池。

### 9. Feedback Chain

feedback 是主求解链和方法沉淀链之间的桥。

当前能力包括：

- 记录一次求解的 route decision、rule ids 和附加 payload。
- 列出所有 feedback。
- 查询单个 feedback。
- 把 feedback 提升为 draft 的起点输入。

对应动作包括：

- `feedback.record`
- `feedback.list`
- `feedback.get`
- `factory.feedback.promote_to_draft`

### 10. Dataset And Replay Chain

这条链主要服务于离线验证、导入、回放和重跑。

当前能力包括：

- 校验一个 dataset 目录是否符合 schema。
- 导入 dataset。
- 输出导入摘要。
- 回放 dataset 中保存的 execution trace。
- 重跑 runtime 并和历史 trace 比较。
- 在 rerun 时把已发布的方法版本合并进运行时规则池，验证方法沉淀是否真的改变系统行为。
- 提供一键完整工作流，串起 validate、import、summary、replay、rerun。

对应动作包括：

- `dataset.validate`
- `dataset.import`
- `dataset.summary`
- `dataset.replay`
- `dataset.rerun`
- `workflow.full`

### 11. Registry And Workflow Orchestration Chain

这条链负责把 dataset 和 workflow run 管起来，方便批量运行、异步任务和历史记录查询。

当前能力包括：

- 注册 dataset。
- 列出和查询 dataset registry。
- 提交异步 workflow run。
- 提交同步 workflow run。
- 列出和查询 workflow run。

对应动作包括：

- `registry.dataset.register`
- `registry.dataset.list`
- `registry.dataset.get`
- `registry.workflow.run`
- `registry.workflow.run_sync`
- `registry.workflow.list`
- `registry.workflow.get`

### 12. Prototype And Demo Chain

这是主产品链之外的演示和快速验证链。

当前能力包括：

- 列出 prototype flow。
- 执行 prototype flow。
- 列出内置 demo workspace case。
- 加载单个 demo case。
- 在 `/prototype` 页面上按 flow 演示“问题 -> 方法匹配 -> 求解 -> 方法沉淀”的链路。

对应动作包括：

- `prototype.flow.list`
- `prototype.flow.run`
- `demo.workspace_case.list`
- `demo.workspace_case.get`

### 13. Ops And Observation Chain

这条链负责让系统“可看见、可回放、可审查”。

当前能力包括：

- `/ops` 查看方法生命周期状态。
- `/console` 查看记录。
- 查看 `workspace_run`、feedback、draft、review、rule version、rollback。
- 查看当前 embedding backend 和可用 backend。
- 查看 trace 和执行轨迹。
- 查看 `orchestration_view`、`asset_pipeline`、`runtime_skill_spec_preview` 等中间产物。
- 通过 `GET /health` 做基础监控。

这条链本质上不是“求解能力”，但它决定了这个系统是不是一个可以长期演进的方法平台。

## API Action Map By Chain

为了便于从接口视角理解系统，下面把当前 action 按功能链归类：

### Main Product Chain

- `product.scenario.list`
- `product.solve.preview`
- `product.workspace.contract`
- `product.workspace.solve`
- `retrieval.embedding_backend.status`
- `super_agent.run`

### Dataset And Replay Chain

- `dataset.validate`
- `dataset.import`
- `dataset.summary`
- `dataset.replay`
- `dataset.rerun`
- `workflow.full`

### Registry Chain

- `registry.dataset.register`
- `registry.dataset.list`
- `registry.dataset.get`
- `registry.workflow.run`
- `registry.workflow.run_sync`
- `registry.workflow.list`
- `registry.workflow.get`

### Prototype And Demo Chain

- `prototype.flow.list`
- `prototype.flow.run`
- `demo.workspace_case.list`
- `demo.workspace_case.get`

### Method Accumulation Chain

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

### Feedback Chain

- `feedback.record`
- `feedback.list`
- `feedback.get`

## Current Boundaries

虽然功能链已经打通，但当前系统仍然有明确边界：

- 它是实验平台，不是生产多租户平台。
- 当前 parser 已经接入主链，但 fact_sheet 仍以 signal-based grounding 为主，不是完整值级事实抽取。
- super agent 已经进入主链，但仍然是轻量回答层，不代表系统已经具备完整的通用多智能体协同能力。
- exploration 已经可以接入外部多智能体发现系统，但这条链仍然更适合研究和沉淀，不适合作为高风险场景的自动最终裁决。

## Reading Guide

如果你想按“功能链”继续顺着看代码，推荐顺序是：

1. `README.md`
2. `SYSTEM_OVERVIEW.md`
3. `API_CONTRACT.md`
4. `product/workspace_flow.py`
5. `product/workspace_runtime.py`
6. `runtime_core/runtime.py`
7. `analysis/exploration_runtime.py`
8. `agents/super_agent_service.py`
9. `factory/*`

如果你想按“页面入口”理解系统，推荐顺序是：

1. `/workspace`
2. `/prototype`
3. `/ops`
4. `/api/phase1`

