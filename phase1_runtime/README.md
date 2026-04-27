# Phase 1 Runtime

`phase1_runtime` 是当前可运行的实验平台实现。

它当前服务于：

- `/workspace`
- `/prototype`
- `/ops`
- `POST /api/phase1`

这份文档只负责：

- 告诉你怎么启动
- 告诉你从哪里进入
- 告诉你下一步该看哪份文档

不负责详细解释系统分层，也不负责记录当前状态判断。

## Quick Start

启动 HTTP 服务：

```bash
python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8010
```

打开页面：

- `http://127.0.0.1:8010/workspace`
- `http://127.0.0.1:8010/prototype`
- `http://127.0.0.1:8010/ops`

健康检查：

```bash
curl -sS http://127.0.0.1:8010/health
```

## Common Commands

函数式 API：

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"product.workspace.solve","question_text":"是否需要发送借款人通知？","materials":[]}'
```

demo case：

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn --check-expected
```

dataset workflow：

```bash
python3 -m phase1_runtime.datasets.dataset_workflow
```

formal schemas：

```bash
python3 -m phase1_runtime.contracts.formal_schemas
```

全量测试：

```bash
python3 -m unittest discover -s phase1_runtime/tests
```

## Read Next

如果你要看系统结构：

- [LAYER_MAP.md](/home/u2023312337/self_learning/phase1_runtime/LAYER_MAP.md)
- [SYSTEM_OVERVIEW.md](/home/u2023312337/self_learning/phase1_runtime/SYSTEM_OVERVIEW.md)

如果你要看当前实现状态：

- [CURRENT_PROJECT_STATUS.md](/home/u2023312337/self_learning/docs/project/CURRENT_PROJECT_STATUS.md)

如果你要看 API：

- [API_CONTRACT.md](/home/u2023312337/self_learning/phase1_runtime/API_CONTRACT.md)

如果你要看目标系统而不是当前实现：

- [TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md](/home/u2023312337/self_learning/docs/project/TARGET_FINANCIAL_RULE_ASSET_PLATFORM_SPEC.md)
