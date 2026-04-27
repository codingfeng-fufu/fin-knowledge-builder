# Fin Knowledge Builder

金融知识构建器 / Financial Knowledge Builder

## 中文说明

Fin Knowledge Builder 是一个面向金融规则、业务方法和知识资产沉淀的实验系统。它不是单纯的 Chat with PDF，而是从“问题 + 文档”出发，完成材料理解、方法匹配、结构化求解、多智能体探索，并把一次求解过程沉淀为后续可复用的规则/方法资产。

核心链路：

```text
问题 + 文档
-> 文档解析与上下文构建
-> 规则/方法检索
-> runtime 执行与 skill 绑定
-> super agent 生成处理意见
-> trace / feedback / draft / review / publish
-> 进入下一轮复用
```

### 核心能力

- 文档理解：支持文本、PDF、DOCX、XLSX、HTML 等材料解析和 query-aware context 构建。
- 结构化求解：根据场景匹配已有规则，支持直接命中、规则组合、补充上下文和探索分流。
- 方法沉淀：把一次求解的证据、轨迹和处理逻辑转成可审核、可发布、可回滚的方法资产。
- 多智能体探索：在现有规则不足时，通过 Problem Framer、Evidence Explorer、Rule Hypothesizer、Rule Critic 等阶段生成候选规则和处理意见。
- 可视化工作台：提供 workspace、prototype、ops、console 以及独立的多智能体 discovery 页面。

### 目录结构

| 路径 | 说明 |
| --- | --- |
| `phase1_runtime/` | 主运行时系统，包含 HTTP 服务、文档解析、检索、runtime、方法沉淀和页面静态资源。 |
| `muti_agent_exploration/` | 独立多智能体规则发现工作台，包含 Flask 后端和 Vue 前端。目录名沿用当前项目命名。 |
| `demo_cases/` | 可复现实验样例，用于展示 workspace/prototype 能力。 |
| `docs/` | 系统设计、产品说明、当前状态和归档文档。 |
| `plugins/claude-style-pdf-reader/` | PDF 阅读插件示例。 |
| `tools/` | 轻量测试和稳定性检查脚本。 |

### 快速启动：主运行时

在仓库根目录执行：

```bash
python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8010
```

常用入口：

- `http://127.0.0.1:8010/workspace`
- `http://127.0.0.1:8010/prototype`
- `http://127.0.0.1:8010/ops`
- `http://127.0.0.1:8010/console`
- `http://127.0.0.1:8010/health`

运行 demo case：

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn --check-expected
```

运行测试：

```bash
python3 -m unittest discover -s phase1_runtime/tests
```

### 快速启动：多智能体探索工作台

环境要求：

- Node.js >= 18
- Python >= 3.11
- uv

启动方式：

```bash
cd muti_agent_exploration
cp .env.example .env
npm run setup:all
npm run dev
```

默认地址：

- 前端：`http://localhost:3000/discovery`
- 后端：`http://localhost:5001`

如果需要启用真实 LLM 调用，在 `muti_agent_exploration/.env` 中配置：

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

不配置 LLM 时，系统仍可使用启发式模式运行，但探索质量和表达丰富度会受限。

### 仓库范围

本仓库只保留系统本身相关文件。比赛提交材料、PPT/PDF 导出物、本地模型、运行日志、缓存、依赖目录、密钥和环境变量文件不进入 Git。

更多细节可从以下文档开始：

- `phase1_runtime/README.md`
- `phase1_runtime/SYSTEM_FEATURE_CHAIN.md`
- `docs/project/WHAT_WE_BUILT.md`
- `WORKSPACE_MAP.md`

## English

Fin Knowledge Builder is an experimental system for building reusable financial rules, business methods, and knowledge assets. It is not a simple Chat with PDF tool. Starting from a user question and supporting documents, it performs document understanding, method retrieval, structured execution, multi-agent exploration, and asset lifecycle management.

Core flow:

```text
question + documents
-> document parsing and context building
-> rule/method retrieval
-> runtime execution and skill binding
-> super-agent response generation
-> trace / feedback / draft / review / publish
-> reusable knowledge asset
```

### Key Capabilities

- Document understanding for text, PDF, DOCX, XLSX, HTML, and mixed evidence bundles.
- Structured problem solving through direct rule matching, rule composition, missing-context handling, and exploration fallback.
- Knowledge asset lifecycle that turns solved cases into reviewable, publishable, and reusable method assets.
- Multi-agent rule discovery for ambiguous or under-specified scenarios where existing rules are not enough.
- Web workbenches for workspace solving, prototype demos, operations review, console traces, and standalone discovery reports.

### Repository Layout

| Path | Description |
| --- | --- |
| `phase1_runtime/` | Main runtime, including the HTTP server, parsing, retrieval, runtime execution, asset lifecycle, and static UI pages. |
| `muti_agent_exploration/` | Standalone multi-agent rule discovery workbench with a Flask backend and Vue frontend. The directory name is kept as-is for compatibility. |
| `demo_cases/` | Reproducible demo cases for workspace and prototype flows. |
| `docs/` | Design notes, product documents, implementation status, and archived plans. |
| `plugins/claude-style-pdf-reader/` | Example PDF reader plugin. |
| `tools/` | Lightweight test and stability-check scripts. |

### Quick Start: Main Runtime

Run from the repository root:

```bash
python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8010
```

Useful entry points:

- `http://127.0.0.1:8010/workspace`
- `http://127.0.0.1:8010/prototype`
- `http://127.0.0.1:8010/ops`
- `http://127.0.0.1:8010/console`
- `http://127.0.0.1:8010/health`

Run a demo case:

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn --check-expected
```

Run tests:

```bash
python3 -m unittest discover -s phase1_runtime/tests
```

### Quick Start: Multi-Agent Discovery Workbench

Requirements:

- Node.js >= 18
- Python >= 3.11
- uv

Start the workbench:

```bash
cd muti_agent_exploration
cp .env.example .env
npm run setup:all
npm run dev
```

Default URLs:

- Frontend: `http://localhost:3000/discovery`
- Backend: `http://localhost:5001`

To enable real LLM calls, configure `muti_agent_exploration/.env`:

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

Without LLM credentials, the system can still run in heuristic mode, but discovery quality and response richness will be limited.

### Repository Scope

This repository keeps only system-related source code, curated demo cases, and documentation. Competition submission packages, generated slides/PDFs, local models, runtime logs, caches, dependency folders, secrets, and environment files are intentionally excluded from Git.

Recommended reading:

- `phase1_runtime/README.md`
- `phase1_runtime/SYSTEM_FEATURE_CHAIN.md`
- `docs/project/WHAT_WE_BUILT.md`
- `WORKSPACE_MAP.md`
