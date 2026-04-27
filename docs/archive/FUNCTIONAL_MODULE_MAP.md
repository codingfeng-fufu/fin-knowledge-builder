# 当前系统功能模块划分

## 1. 文档目的

这份文档只做一件事：

**把当前系统按“功能模块”重新拆开。**

这里不按历史阶段、不按路线图、不按设计愿景来讲，而是只按**当前代码已经存在的模块边界**来划分。


## 2. 总体模块图

当前系统可以按下面 10 个功能模块理解：

```text
1. 入口与页面层
2. 工作台产品层
3. 文档解析与上下文桥接层
4. 规则资产检索层
5. 路由编译与执行层
6. Exploration 与编排层
7. Rule Factory / 资产生命周期层
8. Registry / Dataset / Workflow 层
9. 演示样本与案例运行层
10. 测试与观测层
```

如果按主链串起来，就是：

```text
入口层
-> 工作台产品层
-> 文档解析与上下文桥接层
-> 规则资产检索层
-> 路由编译与执行层
-> Exploration / 编排层
-> Rule Factory / 资产生命周期层
```


## 3. 模块清单

## 3.1 入口与页面层

### 职责

- 提供 HTTP 服务
- 暴露 `/workspace`、`/prototype`、`/ops`、`/console`
- 承接前端页面与 `/api/phase1`

### 主要文件

- [api_http.py](/home/u2023312337/self_learning/phase1_runtime/api_http.py)
- [static/product-console.html](/home/u2023312337/self_learning/phase1_runtime/static/product-console.html)
- [static/prototype-console.html](/home/u2023312337/self_learning/phase1_runtime/static/prototype-console.html)
- [static/ops-console.html](/home/u2023312337/self_learning/phase1_runtime/static/ops-console.html)
- [static/registry-console.html](/home/u2023312337/self_learning/phase1_runtime/static/registry-console.html)

### 输入

- 浏览器请求
- `/api/phase1` JSON 请求

### 输出

- HTML 页面
- API JSON 响应

### 当前状态

- 已成型
- 仍属于原型前端，不是最终产品 UI


## 3.2 工作台产品层

### 职责

- 定义 `/workspace` 的产品入口语义
- 管理场景、默认问题、工作台契约
- 承接 `product.workspace.solve`
- 输出工作台结果对象

### 主要文件

- [product_service.py](/home/u2023312337/self_learning/phase1_runtime/product_service.py)
- [product_catalog.py](/home/u2023312337/self_learning/phase1_runtime/product_catalog.py)
- [product_preview.py](/home/u2023312337/self_learning/phase1_runtime/product_preview.py)
- [workspace_flow.py](/home/u2023312337/self_learning/phase1_runtime/workspace_flow.py)
- [document_parser_contract.py](/home/u2023312337/self_learning/phase1_runtime/document_parser_contract.py)

### 输入

- `question_text`
- `materials[]`
- `scenario_id?`

### 输出

- `solution_view`
- `fact_sheet`
- `document_packet_preview`
- `orchestration_view`
- `asset_pipeline`
- `embedding_backend`
- `task_context`
- `rule_bindings`
- `runtime_skill_spec_preview`

### 当前状态

- 已成型
- 是当前主入口


## 3.3 文档解析与上下文桥接层

### 职责

- 把上传文档转成统一文本/行项结构
- 转成 `DocumentChunk[]`
- 做 required input signal detection
- 生成 signal-based `fact_sheet`
- 生成 `question_packet / document_packet_preview / document_chunks`

### 主要文件

- [document_parser_mvp.py](/home/u2023312337/self_learning/phase1_runtime/document_parser_mvp.py)
- [workspace_parser.py](/home/u2023312337/self_learning/phase1_runtime/workspace_parser.py)
- [document_chunk.py](/home/u2023312337/self_learning/phase1_runtime/document_chunk.py)
- [signal_detector.py](/home/u2023312337/self_learning/phase1_runtime/signal_detector.py)
- [document_parser_contract.py](/home/u2023312337/self_learning/phase1_runtime/document_parser_contract.py)

### 输入

- `txt / html / pdf / docx / xlsx`
- 用户问题
- 场景 seed facts / seed evidence

### 输出

- `parsed_materials`
- `Document Packet Preview`
- `FactSheet`
- `DocumentChunks`
- `missing_fact_keys`
- `QuestionStruct` bridge

### 当前状态

- MVP
- 当前已更接近 signal-based context bridge
- 不是最终版上下文 grounding 系统


## 3.4 规则资产检索层

### 职责

- 根据问题、facts、evidence 召回规则资产候选
- 做 structured + lexical + fact-aware + semantic 混合打分
- 给 runtime/route 层输出候选结果
- 管理 embedding backend 选择与可用状态

### 主要文件

- [retrieval.py](/home/u2023312337/self_learning/phase1_runtime/retrieval.py)
- [retrieval_query.py](/home/u2023312337/self_learning/phase1_runtime/retrieval_query.py)
- [asset_index.py](/home/u2023312337/self_learning/phase1_runtime/asset_index.py)
- [hybrid_retrieval.py](/home/u2023312337/self_learning/phase1_runtime/hybrid_retrieval.py)
- [hybrid_retrieval_types.py](/home/u2023312337/self_learning/phase1_runtime/hybrid_retrieval_types.py)
- [embedding_backend.py](/home/u2023312337/self_learning/phase1_runtime/embedding_backend.py)
- [embedding_backend_service.py](/home/u2023312337/self_learning/phase1_runtime/embedding_backend_service.py)
- [semantic_similarity.py](/home/u2023312337/self_learning/phase1_runtime/semantic_similarity.py)

### 输入

- `QuestionStruct`
- `facts`
- `evidence_refs`
- published rule assets

### 输出

- `MatchResult[]`
- `embedding_backend status`

### 当前状态

- 已从旧的浅层检索升级成混合检索
- 已支持 CPU / GPU backend 选择
- `transformer_model` 后端已接入架构，但当前环境不可直接启用


## 3.5 路由编译与执行层

### 职责

- 决定走 `direct_match / rule_composable / exploration`
- 编译 composition plan
- 补齐 rule inputs
- 生成 step contracts
- 执行 step
- 跑 validator
- 写 trace

### 主要文件

- [compiler.py](/home/u2023312337/self_learning/phase1_runtime/compiler.py)
- [runtime.py](/home/u2023312337/self_learning/phase1_runtime/runtime.py)
- [executors.py](/home/u2023312337/self_learning/phase1_runtime/executors.py)
- [validation.py](/home/u2023312337/self_learning/phase1_runtime/validation.py)
- [trace_store.py](/home/u2023312337/self_learning/phase1_runtime/trace_store.py)
- [schema.py](/home/u2023312337/self_learning/phase1_runtime/schema.py)

### 输入

- candidate rules
- `QuestionStruct`
- `facts`
- `evidence_refs`

### 输出

- `RuntimeResult`
- `ExecutionTrace`
- `composition_plan`
- `feedback`

### 当前状态

- 已成型
- 是当前最稳定的核心主链


## 3.6 Exploration 与编排层

### 职责

- 在 direct/composition 不足时生成 exploration runtime 结果
- 输出候选 case/rule 草稿建议
- 输出 planner/context builder/template/skill/validator 视图

### 主要文件

- [exploration_runtime.py](/home/u2023312337/self_learning/phase1_runtime/exploration_runtime.py)
- [orchestration_layer.py](/home/u2023312337/self_learning/phase1_runtime/orchestration_layer.py)

### 输入

- route failure 或 exploration route
- question / facts / documents / source rules

### 输出

- `exploration_trace`
- `candidate_rule_drafts`
- `case_draft`
- `orchestration_view`

### 当前状态

- MVP
- 能用，但还不是最终强版本


## 3.7 Rule Factory / 资产生命周期层

### 职责

- case ingest
- feedback record
- draft generate
- review create / approve / reject
- publish / rollback
- retrieval asset view
- workspace run 自动沉淀

### 主要文件

- [rule_factory_service.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_service.py)
- [rule_factory_store.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_store.py)
- [rule_factory_feedback.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_feedback.py)
- [rule_factory_workspace.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_workspace.py)
- [rule_factory_retrieval.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_retrieval.py)
- [rule_factory_publish_utils.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_publish_utils.py)
- [rule_factory_validation.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_validation.py)
- [rule_factory_errors.py](/home/u2023312337/self_learning/phase1_runtime/rule_factory_errors.py)

### 输入

- trace
- case
- feedback
- workspace run

### 输出

- draft
- review
- published asset version
- retrieval asset view

### 当前状态

- 已形成最小闭环
- 是当前系统第二条主链


## 3.8 Registry / Dataset / Workflow 层

### 职责

- dataset import / validate / summary
- workflow full run
- registry dataset / workflow persistence
- replay / rerun

### 主要文件

- [dataset_import.py](/home/u2023312337/self_learning/phase1_runtime/dataset_import.py)
- [dataset_consume.py](/home/u2023312337/self_learning/phase1_runtime/dataset_consume.py)
- [dataset_workflow.py](/home/u2023312337/self_learning/phase1_runtime/dataset_workflow.py)
- [registry_store.py](/home/u2023312337/self_learning/phase1_runtime/registry_store.py)
- [registry_service.py](/home/u2023312337/self_learning/phase1_runtime/registry_service.py)
- [registry_worker.py](/home/u2023312337/self_learning/phase1_runtime/registry_worker.py)
- [replay.py](/home/u2023312337/self_learning/phase1_runtime/replay.py)
- [schema_validation.py](/home/u2023312337/self_learning/phase1_runtime/schema_validation.py)

### 输入

- dataset dir
- registered dataset id

### 输出

- import summary
- workflow run
- replay / rerun result

### 当前状态

- 可用
- 更偏支撑层与运营层，不是当前主产品入口


## 3.9 演示样本与案例运行层

### 职责

- 管理 `demo_cases`
- 自动载入演示样本
- 跑 workspace/prototype case

### 主要文件

- [demo_case_service.py](/home/u2023312337/self_learning/phase1_runtime/demo_case_service.py)
- [demo_case_runner.py](/home/u2023312337/self_learning/phase1_runtime/demo_case_runner.py)
- [prototype_service.py](/home/u2023312337/self_learning/phase1_runtime/prototype_service.py)
- [demo_cases](/home/u2023312337/self_learning/demo_cases)

### 输入

- demo case ref
- prototype flow id

### 输出

- loaded materials
- expected subset check
- prototype/workspace run result

### 当前状态

- 已成型
- 用于演示和 smoke


## 3.10 测试与观测层

### 职责

- 单元测试
- 回归测试
- trace 保存
- run payload / logs / ops view

### 主要文件

- [tests](/home/u2023312337/self_learning/phase1_runtime/tests)
- [trace_store.py](/home/u2023312337/self_learning/phase1_runtime/trace_store.py)
- [traces](/home/u2023312337/self_learning/phase1_runtime/traces)
- [consumption_traces](/home/u2023312337/self_learning/phase1_runtime/consumption_traces)

### 当前状态

- 已经比较完整
- 当前全量测试可作为系统稳定性基线


## 4. 当前最重要的主模块

如果只看“当前系统最关键、最应该继续往下做”的模块，不是全部都同等重要。

当前最重要的是 4 个：

1. **工作台产品层**
- 当前主入口就在这里

2. **文档解析与上下文桥接层**
- 这是文档进系统后的第一跳

3. **规则资产检索层**
- 当前已完成混合检索与 embedding backend 架构升级

4. **Rule Factory / 资产生命周期层**
- 这是系统能持续变强的闭环来源


## 5. 当前模块边界的一句话总结

当前系统可以简单理解成：

- **入口层** 负责接用户和页面
- **工作台层** 负责组装产品体验
- **解析桥接层** 负责把文档变成结构化工作输入
- **检索层** 负责找最可能相关的规则资产
- **运行时层** 负责 route 和执行
- **探索/编排层** 负责处理未完全命中的场景
- **资产生命周期层** 负责沉淀、审核、发布与回流

这就是现在系统按功能模块拆开的样子。
