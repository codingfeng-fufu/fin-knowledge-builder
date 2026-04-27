# 当前项目状态

> 以代码为准。
> 本文档只描述当前已经落地的系统结构与主链，不描述历史阶段。

## 当前结论

当前项目已经不是单点原型，而是一个**主链可跑的规则资产平台实验系统**。

当前稳定主链是：

```text
文档 / 问题
-> /workspace
-> parsing
-> retrieval
-> TaskContext / RuleBinding
-> runtime_core
-> skill artifact
-> super agent
-> trace / workspace_run / feedback / draft / review / publish
```

也就是说，系统现在已经具备：

- 文档理解与上下文桥接
- 混合检索与规则绑定
- runtime 执行
- rule -> skill 运行期中间产物
- super agent 最终回答
- factory / registry / feedback 资产闭环

## 当前目录状态

代码目录已经完成分层收敛。

当前目录说明、包职责和 canonical import 约定统一看：

- [phase1_runtime/LAYER_MAP.md](/home/u2023312337/self_learning/phase1_runtime/LAYER_MAP.md)
- [phase1_runtime/SYSTEM_OVERVIEW.md](/home/u2023312337/self_learning/phase1_runtime/SYSTEM_OVERVIEW.md)

## 当前主入口

- `/workspace`
  当前产品主入口，走 `phase1_runtime.product`

- `/prototype`
  原型能力演示入口，走 `phase1_runtime.prototype`

- `/ops`
  规则资产生命周期与运营后台入口，走 `phase1_runtime.factory`

- `POST /api/phase1`
  统一 API 入口，走 `phase1_runtime.api`

## 当前关键实现事实

- PDF 读取主链已经切到 `phase1_runtime.parsing`，当前以 Kimi / plugin 路径为主。
- 检索层当前已经在 `phase1_runtime.retrieval` 中完成分层，不再是顶层散模块。
- runtime 核心已在 `phase1_runtime.runtime_core`。
- rule -> skill 生成已在 `phase1_runtime.skills`。
- 最终回答层已经切到 `phase1_runtime.agents` 里的轻量 super agent，并保留 runtime fallback。
- factory / registry / contracts / datasets 都已经独立成包，不再平铺在顶层。

## 当前仍然成立的边界

- 这仍然是实验系统，不是生产多租户平台。
- skill 已经生成并进入 super agent，但整个系统还不是完整的目标态“多智能体新规则涌现平台”。
- 顶层结构已经基本收敛，后续重点应转回能力建设，而不是继续大规模目录重构。

## 当前建议阅读顺序

- [phase1_runtime/README.md](/home/u2023312337/self_learning/phase1_runtime/README.md)
- [phase1_runtime/SYSTEM_OVERVIEW.md](/home/u2023312337/self_learning/phase1_runtime/SYSTEM_OVERVIEW.md)
- [phase1_runtime/LAYER_MAP.md](/home/u2023312337/self_learning/phase1_runtime/LAYER_MAP.md)
- [phase1_runtime/API_CONTRACT.md](/home/u2023312337/self_learning/phase1_runtime/API_CONTRACT.md)
- [TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md](/home/u2023312337/self_learning/docs/project/TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md)
- [FINANCIAL_RULE_ASSET_PLATFORM_SYSTEM_PROMPT.md](/home/u2023312337/self_learning/docs/project/FINANCIAL_RULE_ASSET_PLATFORM_SYSTEM_PROMPT.md)
