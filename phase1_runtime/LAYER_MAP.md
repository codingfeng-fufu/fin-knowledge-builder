# Layer Map

本文件描述 `phase1_runtime` 当前已经落地的**物理目录分层**，不是目标态草图。

## Current Top Level

当前顶层只保留少量共享基元：

- `phase1_runtime/__init__.py`
- `phase1_runtime/schema.py`
- `phase1_runtime/catalog.py`
- `phase1_runtime/replay.py`
- `phase1_runtime/kimi_llm_executor.py`

这些文件要么是全局 schema / trace / 低层 LLM executor，要么是历史兼容入口。

## Package Layout

- `phase1_runtime/api`
  - API request coercion、dispatch、service wrapper、HTTP server
  - 当前对外 API canonical 入口

- `phase1_runtime/product`
  - `/workspace` 与产品预览主链
  - 包括 scenario catalog、preview、workspace flow

- `phase1_runtime/prototype`
  - 原型流与 demo workspace case 入口

- `phase1_runtime/factory`
  - 规则资产生命周期链
  - 包括 feedback / draft / review / publish / workspace_run / retrieval asset view

- `phase1_runtime/agents`
  - 轻量 super agent
  - 包括 agent loop、tool set、service handoff

- `phase1_runtime/skills`
  - runtime skill creator / Kimi skill creator client / skill materialization

- `phase1_runtime/parsing`
  - 文档解析层
  - 包括 document parser、PDF understanding、workspace parser、document chunks

- `phase1_runtime/retrieval`
  - 检索层
  - 包括 hybrid retrieval、retrieval query、embedding backend、case retrieval、asset index

- `phase1_runtime/runtime_core`
  - 执行核心层
  - 包括 compiler、runtime、executors、rule binding、task context、validation、trace store

- `phase1_runtime/registry`
  - dataset/workflow registry 与 worker

- `phase1_runtime/contracts`
  - data models、formal schemas、schema validation

- `phase1_runtime/datasets`
  - dataset import / consume / workflow orchestration

- `phase1_runtime/analysis`
  - chunk selection、signal detection、exploration runtime、orchestration view

- `phase1_runtime/tools`
  - demo / data generation / demo case runner 等非产品主链工具

## Canonical Imports

新增代码优先从这些包入口 import：

- `phase1_runtime.api`
- `phase1_runtime.product`
- `phase1_runtime.prototype`
- `phase1_runtime.factory`
- `phase1_runtime.agents`
- `phase1_runtime.skills`
- `phase1_runtime.parsing`
- `phase1_runtime.retrieval`
- `phase1_runtime.runtime_core`
- `phase1_runtime.registry`
- `phase1_runtime.contracts`
- `phase1_runtime.datasets`
- `phase1_runtime.analysis`
- `phase1_runtime.tools`

## Guidance

- 不再新增顶层业务实现文件。
- 如果某个模块属于明确业务层或能力层，应放入对应包，而不是回到顶层。
- 顶层剩余文件后续只应继续减少，不应重新膨胀。
