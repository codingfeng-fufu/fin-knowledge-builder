# Rule Factory / Asset Lifecycle 实现蓝图

## 1. 文档目的

本文件是当前有效的 Rule Factory 实现蓝图，已经吸收了早期核心模块设计文档的内容。

目标不是再解释“为什么要做 Rule Factory”，而是回答：

1. 这个模块在实现上要拆成哪些对象。
2. 每个对象有哪些状态。
3. 关键决策逻辑怎么跑。
4. 当前代码基础上，最小实现顺序应该是什么。

本文件的定位是：

**从模块设计过渡到实现设计。**

## 1.1 当前实现进展

截至当前代码状态，下面四个阶段已经完成：

- Phase A：统一对象语义
- Phase B：feedback 决策层最小闭环
- Phase C：composite rule 最小生命周期
- Phase D：retrieval sync 资产视图

这意味着最小主链已经从：

```text
Case / Trace / Feedback
-> Draft Action Decision
-> Draft
-> Review
-> Publish
-> Retrieval Sync
```

推进到了代码可运行、可测试验证的状态。

仍然没完成的主要项：

- `patch existing asset` 决策（已完成最小版）
- 通用资产关系图层
- `approved_pending_publish` / `needs_revision` 这类更细的审核状态
- 更完整的 review console 与运营工作流
- 规则资产混合检索层


## 1.2 必做 TODO：规则资产混合检索

详细设计见：

- [HYBRID_ASSET_RETRIEVAL_DESIGN.md](/home/u2023312337/self_learning/HYBRID_ASSET_RETRIEVAL_DESIGN.md)

当前代码里的规则召回仍然偏轻，主要依赖：

- `question_types`
- `intents`
- `document_types`
- `query_signals`

这套机制能支撑当前 demo，但它不足以支撑后续真实文档与真实提问方式。

因此，`retrieval.py` 后续必须升级成**规则资产混合检索层**。

这层的职责应当是：

1. 在 published assets、historical cases、patterns 中召回候选资产
2. 同时利用：
   - lexical / BM25 signals
   - semantic embedding signals
   - structured filters
   - parser 抽出的 fact features
3. 只负责“找候选资产”，不直接替代最终执行判断

也就是说，新的架构应当变成：

```text
workspace parser
-> hybrid asset retrieval
-> direct_match / composition / exploration gate
-> execution
```

这里要强调：

**目标不是把系统做成普通 RAG，而是让规则资产召回更像一个真正可扩展的检索层。**


## 2. 当前基础与改造方向

当前代码里已经存在的雏形：

- `case_store`
- `candidate_rule_draft_store`
- `review_task_store`
- `published_rule_version_store`
- `case_rule_link_store`
- `rollback_store`
- `feedback_store`

相关文件：

- [rule_factory_store.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_store.py)
- [rule_factory_service.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_service.py)
- [test_rule_factory.py](/home/u2023312337/self_learning/phase1_runtime/tests/test_rule_factory.py)

也就是说：

**数据表已经有了最小雏形，但模型还停留在“规则版本管理”视角，没有升级成“资产生命周期模块”。**

接下来要做的不是推翻，而是：

- 先保留现有 `rule` 主线
- 再把它扩成通用 `asset lifecycle`


## 3. 核心对象模型

## 3.1 第一层：输入池对象

这层对象来自运行与人工操作，是 Rule Factory 的入口。

### A. `FactoryCase`

对应现在的 `case_store`。

最小字段：
- `case_id`
- `dataset_id`
- `scenario_name`
- `dataset_dir`
- `question_text`
- `review_status`
- `payload`
- `created_at`
- `updated_at`

作用：
- 存放可被资产化处理的案例

### B. `FactoryFeedback`

对应现在的 `feedback_store`。

最小字段：
- `feedback_id`
- `trace_id`
- `case_id`
- `route_decision`
- `feedback_type`
- `rule_ids[]`
- `payload`
- `created_at`

作用：
- 存放“为什么这次运行还不够好”的结构化输入

### C. `FactoryTraceRef`

当前代码里还没有显式对象，但逻辑上需要。

最小字段：
- `trace_id`
- `route_decision`
- `matched_rule_id`
- `source_rule_ids[]`
- `final_decision`
- `failure_reason`
- `trace_path`

作用：
- 让 Rule Factory 可以显式消费 trace，不是只靠 case/draft 间接访问


## 3.2 第二层：资产草稿对象

### `AssetDraft`

当前可以先复用 `candidate_rule_draft_store`，但字段语义要升级。

建议字段：
- `draft_id`
- `asset_type`
  - `atomic_rule`
  - `composite_rule`
  - `composition_pattern`
  - `validator_pattern`
  - `evidence_pattern`
- `asset_id`
- `case_id`
- `source_trace_ids[]`
- `based_on_asset_ids[]`
- `status`
- `change_type`
  - `new`
  - `patch`
  - `deprecate`
- `payload`
- `change_summary`
- `created_at`
- `updated_at`

当前最小落地建议：
- 先只支持 `atomic_rule` / `composite_rule`
- 先只支持 `new` / `patch`


## 3.3 第三层：审核对象

### `ReviewTask`

当前已有 `review_task_store`。

建议补强字段语义：
- `review_task_id`
- `target_type`
  - `asset_draft`
- `target_id`
- `status`
  - `open`
  - `approved`
  - `rejected`
  - `needs_revision`
- `assignee`
- `checklist`
- `result_note`
- `created_at`
- `updated_at`

当前最小实现中：
- `needs_revision` 可以先预留，不立刻用上


## 3.4 第四层：已发布资产对象

### `PublishedAssetVersion`

当前已有 `published_rule_version_store`。

建议统一成资产视角：
- `asset_version_id`
- `asset_type`
- `asset_id`
- `version_label`
- `status`
  - `published`
  - `rolled_back`
  - `deprecated`
- `source_draft_id`
- `payload`
- `created_at`

当前最小实现中：
- 可以继续沿用 `rule_version_id / rule_id`，但服务层开始按 `asset` 概念组织


## 3.5 第五层：关系对象

### `AssetLink`

当前已有 `case_rule_link_store`，但关系类型过窄。

建议扩为通用关系对象：
- `link_id`
- `from_type`
- `from_id`
- `to_type`
- `to_id`
- `relation_type`
- `created_at`

关系举例：
- `case -> source_case -> asset_version`
- `feedback -> updates -> draft`
- `asset_version -> supersedes -> asset_version`
- `atomic_rule -> part_of -> composite_rule`

当前最小落地中：
- 先保留现有表结构
- 服务层补充统一关系语义


## 4. 状态机设计

## 4.1 `FactoryCase` 状态机

建议状态：
- `ingested`
- `validated`
- `linked`
- `superseded`

最小规则：
- dataset case 一进入工厂就是 `ingested`
- 一旦进入某个已发布资产的来源集合，可标记 `linked`

当前代码里：
- 还没有真正显式状态机
- 先用 `review_status + links` 近似表示

## 4.2 `AssetDraft` 状态机

建议状态：
- `draft`
- `under_review`
- `approved_pending_publish`
- `published`
- `rejected`
- `needs_revision`

最小状态流：

```text
draft
-> under_review
-> approved_pending_publish
-> published
```

或：

```text
draft
-> under_review
-> rejected
```

当前代码里：
- `draft -> under_review -> published/rejected`

建议下一步：
- 增加 `approved_pending_publish`，让“审核通过”和“真正发布”语义拆开

## 4.3 `ReviewTask` 状态机

建议状态：
- `open`
- `approved`
- `rejected`
- `needs_revision`

规则：
- `open` 才允许审批
- `approved/rejected/needs_revision` 为终态

## 4.4 `PublishedAssetVersion` 状态机

建议状态：
- `published`
- `rolled_back`
- `deprecated`

规则：
- 一次版本只能由一个 draft 产生
- rollback 不删除历史，只改变状态
- deprecated 表示仍可查，但不再优先召回


## 5. 核心决策逻辑

## 5.1 Ingest 决策

输入：
- `case`
- `trace`
- `feedback`

输出：
- 是否生成 draft
- 生成哪类 draft

决策函数建议：

### `classify_case_for_asset_action(case, trace, feedback, published_assets)`

输出动作类型：
- `no_action`
- `new_atomic_rule`
- `new_composite_rule`
- `patch_asset_scope`
- `patch_asset_validator`
- `patch_asset_evidence`

## 5.2 Draft 生成决策

### `generate_asset_draft(action_type, inputs...)`

按动作类型生成不同草稿：

- `new_atomic_rule`
  - 从 case solution steps 中抽最小复用单元
- `new_composite_rule`
  - 从多个 atomic outputs 的稳定编排中提取组合
- `patch_asset_scope`
  - 调整适用范围 / non_scope / trigger
- `patch_asset_validator`
  - 增补 validator 条件

## 5.3 Review 决策

### `build_review_checklist(asset_type, change_type)`

不同资产类型需要不同 checklist：

- `atomic_rule`
  - 输入输出是否清晰
  - 是否可独立校验
  - 是否边界明确
- `composite_rule`
  - 子规则来源是否可追溯
  - 组合关系是否显式
  - binding 是否稳定

## 5.4 Publish 决策

### `publish_asset_draft(draft_id)`

发布前必须检查：

- provenance 完整
- review 已通过
- draft payload 通过 schema 校验
- source validation 通过
- 与现有 published assets 的冲突可解释

## 5.5 Retrieval Sync 决策

### `build_retrieval_asset_view(published_assets)`

职责：
- 统一产出 retrieval 可消费资产视图
- direct match 和 composition 共享它

输出至少包含：
- `asset_id`
- `asset_type`
- `status`
- `trigger`
- `applicability`
- `composition metadata`
- `version_label`


## 6. 当前代码与目标设计的差距

### 已有
- case ingest
- draft generate
- review create/approve/reject
- publish
- rollback
- feedback record
- published rules merge into runtime

### 缺口
- 还没有真正的 `asset_type` 通用模型
- 还没有 draft change_type
- 还没有反馈分类到 draft action 的决策层
- 还没有 composite rule 的正式生命周期
- 还没有通用关系图层
- retrieval sync 仍然偏规则视角，不是资产视角


## 7. 最小实现顺序

## Phase A. 先统一对象语义

目标：
- 不改太多表，但在 service 层先用统一资产语义组织

动作：
1. 给 draft payload 增加：
- `asset_type`
- `change_type`
- `source_trace_ids[]`
- `based_on_asset_ids[]`

2. 给 published payload 增加：
- `asset_type`
- `asset_id`
- `supersedes?`

3. 给 feedback 增加：
- `classification`
- `recommended_action`

## Phase B. 接入反馈决策层

目标：
- feedback 不再只是存储，而是参与草稿生成

动作：
1. 新增：
- `classify_feedback(...)`
- `draft_action_from_feedback(...)`

2. 新增 service：
- `factory.feedback.promote_to_draft`

## Phase C. 接 composite 生命周期

目标：
- 让组合不只存在 runtime plan，而能变成正式资产

动作：
1. Draft 支持 `composite_rule`
2. Publish 支持 `composite_rule`
3. Retrieval 明确支持 `composite_rule`

## Phase D. 做 retrieval sync 资产视图

目标：
- runtime 不再只 merge published rules
- 而是 consume published assets view

动作：
1. 新增：
- `build_retrieval_asset_view()`
2. direct/composition retrieval 共用这层视图


## 8. 对测试的要求

下一步测试不应只验证 CRUD，而应验证闭环。

必须新增的测试类型：

1. `feedback -> draft` 测试
- 一条 missed_rule feedback 能触发 draft 生成

2. `draft -> review -> publish -> retrieval` 测试
- 已发布资产能真正回流到下一次 retrieval

3. `composite_rule lifecycle` 测试
- 组合规则不只是运行时 plan，而能被发布和再次复用

4. `patch existing asset` 测试
- feedback 能触发 patch 而不是总是新建资产


## 9. 一句话总结

如果现在要把最核心模块推进到可实现层，那么最关键的不是继续加页面，而是：

**把 Rule Factory 从“规则版本管理雏形”推进成“资产生命周期引擎”。**

这一步的关键，不在于多写几个 store API，而在于真正打通：

```text
Case / Trace / Feedback
-> Draft Action Decision
-> Draft
-> Review
-> Publish
-> Retrieval Sync
```

只要这条链打通，系统才会从“会跑原型”真正进化成“会成长的平台”。
