# System Overview

这份文档只回答一件事：

**当前系统按什么层次组织。**

不负责：

- Quick start
- 测试状态
- 目标系统愿景

这些分别看：

- [README.md](/home/u2023312337/self_learning/phase1_runtime/README.md)
- [CURRENT_PROJECT_STATUS.md](/home/u2023312337/self_learning/docs/project/CURRENT_PROJECT_STATUS.md)
- [TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md](/home/u2023312337/self_learning/docs/project/TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md)

## User-Facing Surfaces

- `/workspace`
- `/prototype`
- `/ops`
- `POST /api/phase1`

## Package Map

### `phase1_runtime.api`

作用：

- request coercion
- dispatch
- function-style API
- HTTP server

### `phase1_runtime.product`

作用：

- `/workspace` 主链
- product scenario catalog
- preview flow
- workspace solve

### `phase1_runtime.prototype`

作用：

- prototype flow
- demo workspace case 入口

### `phase1_runtime.parsing`

作用：

- document parser
- PDF understanding
- workspace parser
- document chunks

### `phase1_runtime.retrieval`

作用：

- retrieval query
- hybrid retrieval
- embedding backend
- case retrieval
- asset index

### `phase1_runtime.runtime_core`

作用：

- compiler
- runtime
- executors
- rule binding
- task context
- validation
- trace store

### `phase1_runtime.skills`

作用：

- rule -> skill compilation
- skill artifact materialization
- Kimi skill creator client

### `phase1_runtime.agents`

作用：

- lightweight super agent
- tool loop
- runtime skill handoff

### `phase1_runtime.factory`

作用：

- feedback
- draft
- review
- rule version
- workspace run
- retrieval asset lifecycle

### `phase1_runtime.registry`

作用：

- dataset registry
- workflow run registry
- registry worker

### `phase1_runtime.contracts`

作用：

- data models
- formal schemas
- schema validation

### `phase1_runtime.datasets`

作用：

- dataset import
- dataset consume
- dataset workflow

### `phase1_runtime.analysis`

作用：

- chunk selection
- signal detection
- exploration runtime
- orchestration view

### `phase1_runtime.tools`

作用：

- demo runner
- mock data generation
- 非主产品链工具

## Current Main Execution Shape

当前 `/workspace` 主链可以概括为：

```text
question + materials
-> product
-> parsing
-> retrieval
-> runtime_core
-> skills
-> agents
-> factory
```

## Notes

- 当前顶层已经不再承载主要业务实现。
- 顶层剩余文件更多是共享基元或兼容入口。
- 目录细节和 canonical import 约定，以 [LAYER_MAP.md](/home/u2023312337/self_learning/phase1_runtime/LAYER_MAP.md) 为准。
