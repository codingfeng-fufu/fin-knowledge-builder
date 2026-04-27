# 当前实现与目标规格差距清单

对照文档：
[TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md](/home/u2023312337/self_learning/docs/project/TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md)

原则：

- 以代码为准
- 本文档只判断“离目标态还有多远”
- 不重复描述所有现有实现细节

## 总体判断

如果把目标规格视作 `100%`，当前项目大约在 `75%` 左右。

当前已经不是原型拼图，而是：

- 主链可跑
- 前后端可演示
- 多智能体探索已默认接入
- 人工审核与驳回重跑闭环已接通

但它还没有完全达到目标平台形态。

差距主要集中在三类：

1. 规则召回还不是目标态的 rule-RAG
2. 执行层的真实代码/工具能力还没有成为默认稳定主链
3. 候选新方法的测试执行还只是 lightweight preview，不是正式持久化执行链

---

## 一、已基本对齐

### 1. 平台不是单点问答，而是完整主链系统

当前已经具备：

- `/workspace`
- `parsing`
- `retrieval`
- `runtime_core`
- `skills`
- `agents`
- `factory / review / publish`

这条主链已经存在，且可运行。

对应代码：

- [workspace_flow.py](/home/u2023312337/self_learning/phase1_runtime/product/workspace_flow.py)
- [SYSTEM_OVERVIEW.md](/home/u2023312337/self_learning/phase1_runtime/SYSTEM_OVERVIEW.md)

### 2. 常规流程已经具备主干

目标常规流程要求：

- 文档输入
- PDF 阅读与上下文提取
- 规则匹配与验证
- Skill 生成
- 超级 Agent 执行
- 输出最终结果

当前已经基本具备这一整条链。

### 3. 无现成方法时，多智能体探索已接入

现在默认探索后端已经切到：

- [muti_agent_exploration](/home/u2023312337/self_learning/muti_agent_exploration)

接入代码：

- [multi_agent_exploration_adapter.py](/home/u2023312337/self_learning/phase1_runtime/analysis/multi_agent_exploration_adapter.py)
- [workspace_flow.py](/home/u2023312337/self_learning/phase1_runtime/product/workspace_flow.py)

而且已经通过函数级和 HTTP 级验证：

- no-match / exploration 路径默认会进入 `multi_agent_exploration_grounded`

### 4. 人工审核与驳回重跑闭环已具备最小实现

当前已经实现：

- exploration -> feedback -> draft
- draft -> review
- approve -> publish
- reject -> rerun exploration -> new feedback -> new draft -> new review

核心代码：

- [rule_factory_workspace.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_workspace.py)
- [rule_factory_service.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_service.py)
- [rule_factory_feedback.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_feedback.py)

### 5. 审核通过后，规则已真正回流运行时

已发布规则不只是落表保存，而是会被并回运行时规则集：

- [rule_factory_retrieval.py](/home/u2023312337/self_learning/phase1_runtime/factory/rule_factory_retrieval.py)

这一点很关键，说明“入库”不是假动作。

---

## 二、半对齐

### 1. 规则库已存在，但“规则”与“方法”还处于双重语义阶段

对外展示层已经改成：

- 方法
- 解法
- 方法草稿
- 方法沉淀

但内部核心对象仍主要是：

- `Rule`
- `Skill`
- `RuleBinding`

这不是功能问题，但会影响后续长期演进的一致性。

### 2. Skill Creator 已存在，但还没完全做到“用完即弃”

目标规格要求：

- Skill 是运行期中间产物
- 用完即弃
- 不做长期沉淀

当前实现里：

- Skill 会生成
- 也会物化到磁盘用于执行和前端展示

因此它在功能上符合“中间产物”，
但在工程形态上仍偏持久化展示对象。

### 3. 候选新方法的测试执行已存在，但还是 lightweight preview

当前 review 前已经能看到：

- `runtime_preview`
- `method_draft_preview`
- `agent_preview`

这意味着：

- 候选方法并不是“生成后立刻人工审”
- 系统已经先尝试做一轮轻量试跑

但这条链目前还不是：

- 正式独立对象
- 完整持久化 test run
- 强约束的 candidate execution workflow

所以这块属于“有了，但还没完全产品化”。

### 4. Coding 超级 Agent 已部分对齐

当前状态：

- 内置 super agent 仍在
- [mini_coding_agent](/home/u2023312337/self_learning/mini_coding_agent) 已作为可选 backend 接入

接入代码：

- [mini_coding_agent_adapter.py](/home/u2023312337/self_learning/phase1_runtime/agents/mini_coding_agent_adapter.py)
- [super_agent_service.py](/home/u2023312337/self_learning/phase1_runtime/agents/super_agent_service.py)

但它现在还不是默认执行层，
也还没有成为所有复杂任务的统一执行后端。

因此只能算“半对齐”。

### 5. 人工审核模块有了，但审核操作还偏工厂/后台风格

后端闭环已经在，
前端 `/ops` 也能看到：

- 试跑摘要
- review
- reject 后的新 draft / new review

但这部分仍偏运营后台，而不是非常清晰的“产品级审查台”。

---

## 三、未完全对齐

### 1. 规则匹配与验证还不是目标态 rule-RAG

这是当前最核心的差距之一。

目标规格里的匹配逻辑本质上应是：

- 基于高质量 `Context`
- 面向规则库的真正语义检索与适配判断

当前实现仍然主要是：

- structured filter
- trigger / lexical overlap
- 少量 semantic score

也就是 hybrid retrieval，不是目标态 rule-RAG。

对应代码：

- [retrieval](/home/u2023312337/self_learning/phase1_runtime/retrieval)

### 2. PDF Reader Agent 还不够目标态

目标规格要求：

- 全文理解
- 问题聚焦
- 高质量 Context
- 不只是抽文本

当前已经有 query-aware PDF 理解，
但还没有：

- 文档记忆/缓存复用
- 更稳定的全文结构化理解资产复用

所以仍然偏“每次重新解析”的实验态实现。

### 3. 执行层的“真实执行能力”还没完全成为默认主链

目标规格要求执行层默认具备：

- 写代码
- 跑代码
- 调工具
- 回溯证据
- 生成图表

当前虽然已经部分具备：

- 内置 super agent
- mini_coding_agent 可选接入

但还没有做到：

- 默认统一走强执行层
- 自动根据任务类型稳定切换最优执行 backend

### 4. 图表/可视化生成不是当前稳定能力

规格里明确要求：

- 超级 Agent 可以生成图表或可视化结果

当前系统虽然有前端展示和少量图形/流程展示能力，
但“面向用户问题的图表生成”还不是主链稳定能力。

### 5. 审核驳回后的自动迭代虽然有了，但还不是完整多轮闭环调度

现在已有：

- reject -> rerun exploration -> new draft -> new review

但还没有：

- 多轮状态管理
- attempt 历史展示
- 审核意见与 rerun 输入的正式对象化
- 清晰的多轮版本追踪链

所以它是“有闭环”，但还不够“成熟平台化”。

### 6. 当前文档口径仍落后于实现

当前已经做完的变化很多没有同步进：

- [CURRENT_PROJECT_STATUS.md](/home/u2023312337/self_learning/docs/project/CURRENT_PROJECT_STATUS.md)
- [SYSTEM_OVERVIEW.md](/home/u2023312337/self_learning/phase1_runtime/SYSTEM_OVERVIEW.md)

这会导致：

- 代码已经进入“方法/解法”叙事
- 文档仍停在“规则资产平台”旧口径

---

## 四、最关键的剩余差距

如果只挑最重要的三件事，当前离目标规格还差：

### 1. 把规则匹配真正升级成 rule-RAG

这是最重要的底层能力差距。

### 2. 把执行层统一到稳定的真实执行 backend

也就是让：

- 写代码
- 跑工具
- 生成图表
- 复杂计算

成为默认可靠能力，而不是“部分任务可用”。

### 3. 把候选新方法测试执行做成正式对象

现在已经有 preview，
下一步要变成：

- 正式 candidate execution object
- 可追踪
- 可回放
- 可进入审核判断

---

## 五、结论

当前项目已经明显超过“原型拼接态”，
也已经不是“只有演示页面”的空壳。

更准确地说，它现在处于：

**主链已成型、探索与审核闭环已接通、展示面已产品化，但底层检索与执行能力还没完全达到目标规格的阶段。**

如果按目标规格打分：

- 当前约在 `75%`
- 剩余最难、最值钱的部分集中在：
  - rule-RAG
  - 默认强执行层
  - 正式 candidate test execution 链

一句话总结：

**这个项目现在已经有目标平台的骨架和大部分关键环节，但还差最后一段“底层能力收口”才能真正达到目标态。**
