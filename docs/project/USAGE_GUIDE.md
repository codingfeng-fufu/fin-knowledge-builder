# 当前系统使用指南

> 本文档只描述**当前代码已经实现**的使用方式。
> 不讨论未来规划。

## 1. 适用范围

当前系统的主要使用入口有 3 个：

- `/workspace`
  - 主产品入口
  - 用于：上传文档、输入问题、生成建议、查看 `TaskContext / RuleBinding / Skill Preview`

- `/prototype`
  - 系统能力演示入口
  - 用于：演示规则组合与平台能力

- `/ops`
  - 运营后台入口
  - 用于：查看 `workspace_run / feedback / draft / review / version`


## 2. 启动服务

在项目根目录执行：

```bash
python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8013
```

然后打开：

- `http://127.0.0.1:8013/workspace`
- `http://127.0.0.1:8013/prototype`
- `http://127.0.0.1:8013/ops`

健康检查：

```bash
curl -sS http://127.0.0.1:8013/health
```


## 3. Kimi 配置

当前系统已经支持把 **Kimi** 用在两类地方：

1. 文档提取执行（`kimi_llm_executor.py`）
2. rule -> skill 生成（`kimi_skill_creator_client.py`）

### 3.1 环境变量方式

```bash
export MOONSHOT_API_KEY=your_key
export MOONSHOT_BASE_URL=https://api.moonshot.ai/v1
export MOONSHOT_MODEL=kimi-k2.5
export MOONSHOT_TIMEOUT_SECONDS=30
export MOONSHOT_TEMPERATURE=0.2
export MOONSHOT_MAX_TOKENS=3000
export MOONSHOT_THINKING=disabled
```

### 3.2 `config.json` 方式

项目根目录已有 `config.json` 时，也会优先读取其中的 Moonshot 配置。

### 3.3 当前行为

- 如果 Kimi 可用，系统会在需要时尝试调用 Kimi
- 如果 Kimi 不可用，当前很多链路会自动 fallback
- `rule_to_skill_creator` 也会 fallback 到 deterministic template generation


## 4. `/workspace` 的使用方式

### 4.1 页面作用

`/workspace` 是当前系统的主入口。

它会做：

- 文档解析
- 场景识别
- 混合检索
- `TaskContext`
- `RuleBinding`
- runtime 执行
- trace / feedback / draft 写回
- `runtime_skill_spec_preview`

### 4.2 打开后的默认行为

当前页面会：

- 自动加载一条默认 demo case
- 自动生成一次结果

也就是说，打开页面后就能直接看到：

- 文档
- 问题
- 系统输出
- 沉淀资产

### 4.3 使用内置演示样本

页面左侧有：

- `推荐样本`

点任意样本后，系统会自动：

- 填入问题
- 绑定材料
- 执行一次

最推荐的样本是：

- `fund_docx_direct_warn`

### 4.4 手工输入

展开：

- `手工改输入`

可以：

- 手动选择场景
- 输入问题
- 上传材料
- 点击 `生成处理建议`

### 4.5 当前页面上能看到什么

主视图当前优先展示：

- 文档位置
- 问题输入
- 系统输出
- 沉淀资产

折叠区还能看：

- 系统路径
- 解析细节
- 执行编排层
- Skill Preview

### 4.6 Skill Preview

当前 `/workspace` 已经会返回：

- `runtime_skill_spec_preview`

页面里的：

- `查看 Skill Preview`

会显示：

- `skill_name`
- `source_rule_id`
- `skill_type`
- `binding_status`
- `context_status`
- `SKILL.md` 预览

注意：

- 当前只是 **preview**
- 还没有让执行层按这个 skill 去跑


## 5. `/prototype` 的使用方式

### 5.1 页面作用

`/prototype` 更偏系统能力演示，而不是主产品入口。

它适合演示：

- 规则资产平台原型
- 规则组合能力
- 系统工作方式

### 5.2 页面行为

页面默认会自动跑推荐 flow。

你可以直接在页面里切换：

- `fund_compose`
- 其他 prototype flow


## 6. `/ops` 的使用方式

### 6.1 页面作用

`/ops` 是当前的最小运营后台。

它可以查看和操作：

- `Workspace Runs`
- `Feedback Queue`
- `Drafts`
- `Reviews`
- `Rule Versions`

### 6.2 当前页面上能看到什么

顶部会显示：

- 当前 retrieval backend 状态

列表卡片上也会直接显示：

- backend / device
- skill name

尤其在：

- draft
- review
- version

卡片上可以一眼看到这些元数据。

### 6.3 典型操作

在 `/ops` 里可以：

- 查看 workspace runs
- 查看 feedback
- 把 feedback promote 成 draft
- 创建 review
- approve / reject
- rollback published version


## 7. Demo Case 使用方式

当前 demo cases 在：

- [demo_cases](/home/u2023312337/self_learning/demo_cases)

### 7.1 直接跑一个 case

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn --check-expected
```

### 7.2 说明

- `workspace/*`：面向 `/workspace` 的样本
- `prototype/*`：面向 `/prototype` 的样本

如果加 `--check-expected`：

- 会只对关键字段做比对


## 8. API 使用方式

### 8.1 直接调用 API service

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"retrieval.embedding_backend.status"}'
```

### 8.2 常用动作

#### 查看当前检索后端状态

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"retrieval.embedding_backend.status"}'
```

#### 查看内置 workspace demo case

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"demo.workspace_case.list"}'
```

#### 拉取一个具体 demo case

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"demo.workspace_case.get","case_ref":"workspace/fund_docx_direct_warn"}'
```

#### 手动调用 workspace solve

```bash
python3 -m phase1_runtime.api.api_service --payload '{
  "action":"product.workspace.solve",
  "question_text":"某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
  "scenario_id":"fund_nav_warning",
  "materials":[]
}'
```

#### 查看 factory drafts

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"factory.draft.list"}'
```

#### 查看 factory reviews

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"factory.review.list"}'
```

#### 查看 published versions

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"factory.rule_version.list"}'
```


## 9. 测试

当前最新代码基线测试命令：

```bash
python3 -m unittest discover -s phase1_runtime/tests
```

当前结果：

- `Ran 138 tests`
- `OK`


## 10. 当前边界

当前系统已经具备：

- 文档解析
- signal-based context bridge
- hybrid retrieval
- `TaskContext`
- `RuleBinding`
- runtime 执行
- Rule Factory 生命周期
- rule -> skill preview 生成

当前系统还没有做的是：

- skill-driven execution

也就是说：

- 现在已经能生成 skill preview
- 但执行层仍然是当前 runtime 主链
