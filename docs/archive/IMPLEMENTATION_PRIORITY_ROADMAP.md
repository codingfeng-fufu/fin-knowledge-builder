# 后续实施优先级

## 1. 目标

这份文档只回答一个问题：

**在当前代码状态下，接下来应该先做什么，后做什么。**

排序原则不是“设计里什么最酷”，而是：

1. 先补最影响闭环成立的模块
2. 先补 `/workspace` 主入口真正依赖的能力
3. 先补能让规则资产继续增长的链路
4. 暂不优先做展示性但不决定主链成立的模块

---

## 2. 当前基线

当前已经有：

- `Direct Match`
- `Rule Composition`
- 最小 `Rule Factory` 生命周期
- `/workspace` 主入口
- 文本上传 parser bridge
- `question_packet / fact_sheet / evidence_packets -> runtime` 最小桥接

当前还没有：

- 真实 PDF / Word / Excel 文档解析
- 真正的 `Exploration Runtime`
- 工作台到 Rule Factory 的自动沉淀链
- KG / Template / Skill 编排层
- 产品化运营后台

所以当前最合理的推进顺序，不是继续收页面，也不是先上 KG，而是：

**先把“真实输入 -> 求解 -> 沉淀”的主链补完整。**

---

## 3. P0：必须先做

## P0-1. 真实文档解析器 MVP

### 为什么是第一优先级

现在 `/workspace` 已经是主入口，但它仍然只支持：

- 文本上传
- 最小文本事实抽取
- 场景化 fallback

这意味着主入口虽然已经定了，但还不能真正承接真实业务文档。

如果这一步不做，项目就始终停留在“正确形态的原型”，而不是“真正可用的系统入口”。

### 目标

把当前：

`text upload -> minimal parser`

升级成：

`pdf/docx/xlsx/html/msg -> document_set / blocks / tables / evidence locator`

### 必须交付

1. 文档接入层
- 支持 `pdf`
- 支持 `docx`
- 支持 `xlsx`
- 保留 `txt/md/json/csv/log`

2. 统一解析输出
- `document_set`
- `blocks`
- `tables`
- `evidence locator`
- `parse_status`

3. 与当前 runtime 桥接
- 解析结果进入 `question_packet / fact_sheet / evidence_packets`
- `/workspace` 不再依赖样本默认 facts 才能成立

4. 最小回归测试
- 至少两类文档样本
- 至少两类问题族
- 至少一条失败路径

### 成功标准

- 用户上传真实 PDF/Word/Excel 后，`/workspace` 能生成 `document_packet`
- 至少基金和信贷两个业务族能从真实文档里抽出关键 facts
- 系统输出里 evidence locator 来自真实解析结果，而不只是样本 fallback

### 这一步先不做

- OCR 深度优化
- 多语言复杂版面
- 全通用表格理解
- 高级文档版式可视化

---

## P0-2. 工作台到 Rule Factory 的自动沉淀链

当前状态：已完成最小版本。当前 `/workspace` 运行后会自动生成 `workspace_run`，并在适用时自动记录 feedback、自动提升为 candidate draft。

### 为什么是第一优先级

现在工作台已经能产生：

- question packet
- fact sheet
- trace
- feedback defaults

但还没有自然形成：

`workspace run -> feedback -> candidate draft`

这会导致主入口和资产闭环之间仍有断层。

### 目标

让 `/workspace` 成为真正的前台主入口，而不是“能跑结果但沉淀还要手动补”的入口。

### 必须交付

1. 工作台结果记录
- 每次运行产出统一 `workspace_run_record`
- 保存 parser status / route / final answer / trace ref

2. feedback 自动生成入口
- 失败时自动生成初始 feedback
- exploration 时自动生成待沉淀记录
- composition 稳定命中时允许快速提升为 composite candidate

3. 与 Rule Factory 接口贯通
- `workspace run -> feedback.record`
- `feedback -> promote_to_draft`
- 在 UI 或 API 上可追踪

### 成功标准

- 一次 `/workspace` 运行后，系统能直接产生可追踪的沉淀入口
- 不需要开发人员手工拼 payload 才能把结果送进 Rule Factory

---

## 4. P1：第二阶段重点

## P1-1. 真正的 Exploration Runtime

当前状态：已完成最小 MVP。现在 exploration 路径会生成 `exploration_trace / case_draft / candidate_rule_draft suggestions`，并接入 `/workspace` 与自动沉淀链。

### 为什么排在 P1

现在 `exploration` 还更像 fallback 和反馈触发点，不是设计里定义的独立增长引擎。

但在 parser 和工作台主链没稳之前，先做 Exploration 很容易把范围拉炸。

### 目标

实现设计文档中的：

`Direct Match -> Rule Composition -> Exploration Runtime`

其中 Exploration 真正负责：

- 处理前两层都覆盖不了的问题
- 产出 `Case Draft`
- 产出 `Candidate Atomic Rule Draft`
- 产出 `Candidate Composite Rule Draft`

### 必须交付

1. 明确 exploration 输入
- 未命中原因
- 当前 trace
- 当前 facts / evidence
- 候选资产上下文

2. exploration 输出对象
- `case_draft`
- `candidate_rule_draft`
- `exploration_trace`

3. exploration 成功标准
- 不是只给答案
- 而是对规则库有净新增价值

### 成功标准

- exploration 产出能直接接入 Rule Factory
- exploration 不再只是“失败日志”，而是“资产生成前置层”

---

## P1-2. Patch Existing Asset 决策

当前状态：已完成最小版本。系统现在会根据 feedback 的上下文判断是新建 asset，还是 patch 既有 asset（scope / evidence pattern）。

### 为什么排在 P1

当前 Rule Factory 已经能新建 asset，也能走 composite lifecycle。

但如果没有 patch 逻辑，规则库会越来越碎。

### 目标

让系统学会区分：

- 该新建资产
- 还是该 patch 旧资产

### 必须交付

1. `draft_action_from_feedback` 扩展
- `new_atomic_rule`
- `new_composite_rule`
- `patch_asset_scope`
- `patch_asset_validator`
- `patch_asset_evidence`

2. patch provenance
- 明确 supersedes / based_on / source_trace_ids

3. 回归测试
- 同一问题边界变化时，不总是产生新规则

### 成功标准

- 反馈不再默认新建资产
- 规则资产增长开始有“修正”而不只是“堆积”

---

## 5. P2：平台化与终态能力

## P2-1. KG / Template / Skill 编排层

当前状态：已完成最小版。系统现在会基于当前执行路径产出 `kg_subgraph / templates / skills / step_contract_preview / validator_summary`，并接入 `/workspace`。

### 为什么放到 P2

这是完整设计里非常重要的一层，但它不是当前主链最短板。

在 parser、workspace、exploration、asset lifecycle 没打稳之前，上这层容易只变成一个复杂外壳。

### 目标

把：

- 规则关系
- 模板化步骤
- 技能化执行单元
- 上下文裁剪

统一成执行编排层。

### 必须交付

1. 规则关系图谱最小模型
2. template 编译机制
3. skill 下沉标准
4. validator 驱动的执行合同

### 成功标准

- 执行层不再只靠 Rule DSL 直接驱动
- 规则资产开始具备更强的复用与编排能力

---

## P2-2. 运营后台与多用户工作流

当前状态：已完成最小版。现在系统已经提供 `/ops` 运营后台，可查看并操作 `workspace runs / feedback / drafts / reviews / rule versions`。

### 目标

把当前工程式的 store / API 能力升级成：

- review console
- feedback queue
- rule publish console
- rollback / supersede 可视化
- 多用户角色流

### 为什么放到 P2

这类能力很重要，但只有当前台主链和资产增长链稳定后才值得做重投入。

---

## 6. 暂不优先做的事情

以下内容现在都不应排在前面：

1. 继续打磨 demo 页视觉
2. 复杂图谱可视化
3. 多场景横向扩展过快
4. 复杂 multi-agent 架构
5. 大量非核心前端页面

原因很简单：

这些都不会决定“完整 pipeline 是否成立”。

---

## 7. 推荐执行顺序

最推荐的实际顺序是：

1. `P0-1` 真实文档解析器 MVP
2. `P0-2` 工作台到 Rule Factory 的自动沉淀链
3. `P1-1` 真正的 Exploration Runtime
4. `P1-2` Patch Existing Asset 决策
5. `P2-1` KG / Template / Skill 编排层
6. `P2-2` 运营后台与多用户工作流

---

## 8. 一句话结论

如果只看当前代码状态，下一阶段最应该做的不是继续补页面，而是：

**先把真实文档解析器和工作台到 Rule Factory 的自动沉淀链做完。**

只要这两步完成，系统才会从“有闭环原型”进入“真正可持续增长的平台”。
