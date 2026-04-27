# Muti Agent Exploration

一个独立的多智能体规则发现系统。

它的目标不是“从规则库里机械检索答案”，而是围绕 `Query + Context`，结合规则库、文档证据与多智能体协作，发现：

- 哪些规则可以直接复用
- 哪些规则需要在现有规则基础上改造
- 哪些场景需要提出全新的候选规则

系统同时保留完整的推理过程、证据链、来源归因与批判性审查结果，适合做规则研究、规则草案生成和人机协同探索。

## 核心能力

- 多智能体规则发现工作流
- `grounded` / `emergent` 双模式
- 规则库导入、文档导入、Query/Context 处理
- 规则复用、规则改造、候选新规则生成
- Critic 审查
  关系类型包括 `duplicate / supplement / tighten / conflict / analogous`
- 来源归因
  包括 `knowledge_sources / source_provenance / grounding_score / speculation_score`
- 全流程可视化前端工作台
- 独立报告页

## 工作流

系统当前按以下阶段运行：

1. `Problem Framer`
2. `Analogy Miner`
3. `Evidence Explorer`
4. `Rule Hypothesizer`
5. `Rule Critic`
6. `Decision Synthesizer`

同时，在前端工作台中，每个阶段会进一步拆成多个更细的 agent 视角进行展示，例如：

- `Intent Mapper`
- `Constraint Extractor`
- `Ambiguity Mapper`
- `Exact Match Scout`
- `Adaptation Scout`
- `Negative Miner`
- `Support Finder`
- `Risk Finder`
- `Gap Finder`
- `Reuse Drafter`
- `Adaptation Drafter`
- `Novel Rule Drafter`
- `Conflict Critic`
- `Counterexample Critic`
- `Provenance Critic`

## 双模式

### `grounded`

尽量闭卷。

系统应优先只基于以下信息推理：

- 规则库
- 文档证据
- 中间阶段产物

如果候选规则缺乏输入材料支撑，系统应更倾向于输出：

- `insufficient_evidence`
- `need_human_review`

### `emergent`

允许智能涌现。

系统可以在规则库和文档之外，引入通用知识、行业经验或跨域常识参与规则发现，但会显式标记：

- `knowledge_sources`
- `general_knowledge_used`
- `grounding_score`
- `speculation_score`

## 前端页面

独立项目只有两页：

- 工作台：`/discovery`
- 发现报告页：`/discovery/report/:taskId`

工作台提供：

- 规则库编辑
- 文档证据编辑
- Query / Context 输入
- 模式切换
- LLM 开关
- 实时任务轮询
- 多智能体讨论区
- Agent Radar
- 规则对比视图

报告页提供：

- 任务摘要
- 候选规则总览
- 推理轨迹
- Critic 审查结果
- Open Questions
- Rejected / Blocked
- Stage Ledger
- Source Provenance

## 技术栈

前端：

- Vue 3
- Vue Router
- Axios
- Vite

后端：

- Flask
- Flask-CORS
- OpenAI Python SDK 兼容调用
- PyMuPDF
- python-dotenv

## 目录结构

```text
muti_agent_exploration/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── services/
│   │   └── utils/
│   ├── scripts/
│   ├── pyproject.toml
│   └── run.py
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── api/
│   │   ├── router/
│   │   └── views/
│   ├── package.json
│   └── vite.config.js
├── .env.example
└── package.json
```

## 环境要求

- Node.js `>= 18`
- Python `>= 3.11`
- `uv`

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
```

如果你想启用 `use_llm=true`，需要在 `.env` 中填写：

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

不填也能跑，但只能使用启发式模式。

### 2. 安装依赖

```bash
npm run setup:all
```

### 3. 启动项目

```bash
npm run dev
```

默认地址：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:5001`

如果这两个端口被占用，可以自行修改：

- `frontend/vite.config.js`
- `.env` 中的 `FLASK_PORT`

## 独立验证

### 后端 smoke test

```bash
cd backend
uv run python scripts/smoke_test_rule_discovery.py
```

### LLM 长测

```bash
cd backend
uv run python scripts/llm_regression_rule_discovery.py --case grounded_relevant --timeout-seconds 120
```

这个长测脚本采用“发现型任务”成功标准：

- `completed` 视为成功
- `insufficient_evidence` 视为成功
- `need_human_review` 视为成功
- 只有 `failed / timed_out / cancelled / 无结果` 视为失败

## 当前状态

这个项目现在适合：

- 规则研究
- 规则草案生成
- 人机协同探索
- 多智能体推理过程演示

这个项目现在还不建议直接当作：

- 全自动正式规则发布器
- 高风险生产判定引擎

## 说明

项目目录名使用的是 `muti_agent_exploration`，保留当前命名，不在本次改动中重命名。

