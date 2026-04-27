# Rule Factory / Asset Lifecycle 核心模块设计

## 1. 文档目的

本文件回答一个问题：

**如果只看整个系统里最核心、最不可替代的模块，它应该是什么，应该如何设计。**

结论先说：

**最核心模块不是前台问答页，也不是单次 runtime，而是 `Rule Factory / Asset Lifecycle`。**

因为：
- 前台只是入口
- runtime 只是一次执行
- 真正让系统“越用越强”的，是资产闭环

也就是：

```text
Case
-> Draft Rule
-> Review
-> Publish
-> Retrieval
-> Reuse
-> Trace / Feedback
-> Rule Update
```


## 2. 为什么它是最核心模块

根据原始文档：

- [rule_factory_mvp.md](/home/u2023312337/self_learning/rule_factory_mvp.md)
- [financial_rule_asset_final_plan_v4.md](/home/u2023312337/self_learning/financial_rule_asset_final_plan_v4.md)

系统真正想积累的，不是答案文本，而是：

- `Case`
- `Atomic Rule`
- `Composite Rule`
- `Composition Pattern`
- `Evidence Pattern`
- `Validator Pattern`

如果没有 Rule Factory：
- 用户问题最多被处理一次
- runtime 只是在重复执行
- feedback 只是日志
- 规则不会稳定演进

所以最核心模块的职责不是“回答问题”，而是：

**把一次处理经验转成可复用、可审核、可发布、可更新的规则资产。**


## 3. 核心模块的边界

### 3.1 它不负责什么

Rule Factory 不直接负责：

- 文档解析
- 前台交互
- 单步执行器实现
- OCR / table extraction
- 最终答案生成本身

这些属于：
- Document Parser
- Workspace UI
- Runtime / Tooling

### 3.2 它必须负责什么

Rule Factory 必须负责：

1. 接收新的案例与运行痕迹
2. 形成候选规则或规则更新草稿
3. 支持人工审核与发布
4. 管理版本、回滚与关系追踪
5. 让已发布资产重新回流到下一次召回


## 4. 核心闭环

### 4.1 主闭环

```text
Question Execution
-> Trace
-> Feedback
-> Rule Factory
-> Draft
-> Review
-> Publish
-> Asset Store
-> Next Retrieval
```

### 4.2 从资产视角看

```text
Case
-> Abstract
-> Atomic Rule / Composite Rule
-> Validate
-> Publish
-> Reuse
-> Observe Failure / Correction
-> Refine
```

### 4.3 这个模块真正要保证的事

不是“有没有数据库表”，而是：

- 每个 `Case` 能否进入工厂
- 每个 `Trace / Feedback` 能否变成 draft 输入
- 每个 draft 能否经过 review 变成 published asset
- 每个 published asset 能否回到 Retrieval

如果这 4 件事都不能成立，闭环就只是表面闭环。


## 5. 模块输入输出

## 5.1 输入

Rule Factory 的输入不是单一对象，而是 4 类来源：

### A. `Case`

来源：
- 人工整理样本
- Workspace 中用户处理后的归档案例

内容：
- 问题
- 材料
- 金标准答案
- 证据
- 处理步骤
- reviewer / review_status

### B. `ExecutionTrace`

来源：
- Direct Match
- Rule Composition
- Exploration fallback

内容：
- route_decision
- candidate rules
- step contracts
- validator results
- final result
- failure_reason

### C. `FeedbackRecord`

来源：
- 人工反馈
- 手工修正
- missed rule
- composition failure
- bad answer / bad evidence

### D. 已有 `Published Assets`

来源：
- 当前资产库

作用：
- 对比新 case / 新 trace
- 决定是新建规则、补边界、还是更新已有规则


## 5.2 输出

Rule Factory 的输出至少有 5 类：

### A. `Candidate Draft`

表示：
- 一条待审核的候选规则或更新草稿

### B. `Review Task`

表示：
- 需要人工确认的事项

### C. `Published Rule Version`

表示：
- 已审核通过、进入正式资产库的规则版本

### D. `Case-Rule Link`

表示：
- 哪个 case 产生了哪个规则
- 哪个 case 验证了哪个规则

### E. `Rollback Record`

表示：
- 哪次发布被回滚
- 原因是什么


## 6. 核心对象模型

当前最值得锁死的，不是 UI，而是对象模型。

### 6.1 `Case`

最小字段：
- `case_id`
- `question_text`
- `documents`
- `gold_answer`
- `evidence_refs`
- `solution_steps`
- `review_status`
- `source`

### 6.2 `DraftAsset`

这里建议不要只叫 `draft_rule`，因为未来不只是 rule。

最小字段：
- `draft_id`
- `asset_type`
  - `atomic_rule`
  - `composite_rule`
  - `composition_pattern`
  - `validator_pattern`
  - `evidence_pattern`
- `source_case_ids[]`
- `source_trace_ids[]`
- `based_on_rule_ids[]`
- `status`
  - `draft`
  - `under_review`
  - `published`
  - `rejected`
- `payload`
- `change_summary`

### 6.3 `ReviewTask`

最小字段：
- `review_task_id`
- `target_type`
- `target_id`
- `review_checklist`
- `assignee`
- `status`
- `result_note`

### 6.4 `PublishedAssetVersion`

最小字段：
- `asset_version_id`
- `asset_type`
- `asset_id`
- `version_label`
- `status`
- `source_draft_id`
- `payload`
- `created_at`

### 6.5 `AssetLink`

最小字段：
- `link_id`
- `from_type`
- `from_id`
- `to_type`
- `to_id`
- `relation_type`

例子：
- `case -> derived_from -> atomic_rule`
- `atomic_rule -> composed_into -> composite_rule`
- `feedback -> updates -> published_asset`


## 7. 模块内部子模块

### 7.1 Ingest Layer

职责：
- 接收 case / trace / feedback
- 做基本校验
- 统一写入工厂输入池

### 7.2 Asset Draft Generator

职责：
- 根据新 case 或 feedback 生成草稿
- 判断这是：
  - 新规则
  - 旧规则补边界
  - 组合模式补充
  - validator/evidence pattern 补充

### 7.3 Review Manager

职责：
- 创建 review task
- 管理 checklist
- 审批 / 驳回

### 7.4 Publish Manager

职责：
- 生成正式版本
- 维护版本号
- 维护发布状态
- 记录 provenance

### 7.5 Linkage Manager

职责：
- 建立 case / trace / feedback / rule version 之间的关系图

### 7.6 Retrieval Sync Layer

职责：
- 把已发布资产导出到 Retrieval 可消费的资产视图
- 让下一次问题优先用最新资产


## 8. 核心决策逻辑

这个模块内部最关键的不是 CRUD，而是判断逻辑。

### 8.1 新 case 进入后，应该怎么处理

应该先问：

1. 这个 case 是否已被现有 published asset 覆盖？
2. 如果没有覆盖，是缺整题规则，还是缺 atomic rules？
3. 如果已有规则覆盖但人工改了答案，是规则错、边界不清，还是 validator 不够？

输出应落到这几种动作之一：

- `create_new_atomic_rule`
- `create_new_composite_rule`
- `patch_existing_rule_scope`
- `patch_existing_validator_pattern`
- `patch_existing_evidence_pattern`
- `no_action_needed`

### 8.2 Feedback 进入后，应该怎么处理

Feedback 不应该直接只入库。

必须先分类：

- `missed_rule`
- `wrong_rule_selected`
- `insufficient_evidence`
- `bad_final_answer`
- `composition_failed`
- `needs_new_atomic_rule`
- `needs_scope_refinement`

不同类型进入不同 draft 生成逻辑。


## 9. 它与 runtime 的关系

Rule Factory 不替代 runtime。

两者关系应该是：

```text
Runtime solves current question
Rule Factory updates asset base
Updated assets feed next runtime retrieval
```

换句话说：

- Runtime 解决当前问题
- Rule Factory 负责下一次问题更好解决

如果让 Rule Factory 直接承担 runtime 的职责，系统会混乱。


## 10. 它与前台工作台的关系

前台工作台只负责：

- 输入问题与材料
- 展示答案与依据
- 提交 feedback

真正的资产生产动作：

- 生成 draft
- 审核
- 发布
- 回滚

都应该落在 Rule Factory 里。

所以正确关系是：

```text
Workspace
-> Trace / Feedback
-> Rule Factory
-> Published Assets
-> Workspace reuse
```


## 11. 最小可落地版本

### MVP-1

目标：
- 工厂能吃下 `Case + Trace + Feedback`
- 能生成 `draft_rule`
- 能走 review / publish
- 已发布规则能回流 retrieval

### MVP-2

目标：
- 支持 `Atomic Rule / Composite Rule / Composition Pattern` 三类资产
- 支持 feedback 分类处理

### MVP-3

目标：
- 支持已有 published asset 的差异比较
- 支持 patch 而不只是新建 rule
- 支持更完整的规则演进链


## 12. 这就是当前最核心模块的原因

如果只选一个模块，优先做这个模块是因为：

- 没有它，系统不会变强
- 没有它，runtime 只是一次性求解器
- 没有它，前台工作台只是问答界面
- 没有它，整个项目最核心的价值闭环就不成立

所以，**Rule Factory / Asset Lifecycle 不是系统的一个附属后台，而是系统真正的增长引擎。**


## 13. 一句话总结

当前项目里最核心的模块应该被定义为：

**负责把 Case / Trace / Feedback 持续转化为可发布、可复用、可更新规则资产的核心资产生命周期模块。**

如果这个模块没有被设计清楚，整个系统最终就会退化成：
- 一个会答题的系统
- 或一个存规则的后台

而不是你们原来想做的金融规则资产平台。
