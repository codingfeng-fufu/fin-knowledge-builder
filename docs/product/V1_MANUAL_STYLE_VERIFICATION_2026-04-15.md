# V1 手工风格验证记录（2026-04-15）

> 说明：当前环境没有可用的本地浏览器自动化依赖（无 Playwright / Selenium / 本地浏览器），因此本次验证采用：
>
> - live HTTP 页面检查
> - API 返回检查
> - 前端状态机源码检查
>
> 这不是“真实浏览器点点点”的最终替代，但足以提前发现大多数配置、入口和信息架构问题。

## 1. 服务状态

- `http://127.0.0.1:8014/health`：正常

## 2. 四个核心入口标题

- `/workspace` -> `金融文档求解工作台`
- `/workflow` -> `系统说明`
- `/ops` -> `内部治理后台`
- `/demo` -> `导演版演示`

结论：

- 四个入口的页面标题已经和 V1 定义一致。

## 3. 默认样本检查

通过 `demo.workspace_case.list` 与 `demo.workspace_case.get` 验证：

- `default_case_ref = workspace/fund_docx_direct_warn`
- `default_case_title = 基金预警判断：是否需要风险提示`
- `default_case_scenario_id = fund_nav_warning`
- `default_material_count = 1`
- `default_question_text = 某私募产品净值跌破0.80后，是否需要向投资者做风险提示？`

结论：

- 当前默认体验已经切回 fund warning。

## 4. `/workspace` 首次进入逻辑（源码状态机检查）

在 `phase1_runtime/static/workspace-app.js` 中确认：

- `startIntent` 默认是 `sample`
- `state.defaultSampleRef` 会接收 `demo.workspace_case.list` 返回值
- `init()` 中在取到 `default_case_ref` 后，会执行 `await loadSample(state.defaultSampleRef)`
- `activeSolveInputs()` 在 sample 模式下会使用 `selectedSample.materials`
- 在 upload 模式下只使用 `uploadedFiles`

结论：

- 从源码逻辑上，首次进入时默认样本会被预载入
- 样本模式 / 上传模式的切换逻辑已存在且互斥

## 5. 当前文案口径检查

### `/workspace`

已确认页面存在：

- Hero 主标题：`让每一次回答，都成为下一次的能力`
- Hero 副标题：`把答案变成规则，把规则变成系统持续进化的起点。`
- 起步双路径
- `结果概览`
- `判断依据 / 状态说明 / 内部记录`
- `换一种问法`

### `/workflow`

已确认页面口径是：

- `系统说明`
- `已有方法 / 进入内部处理`

### `/ops`

已确认页面口径是：

- `内部治理后台`
- `从一次求解，走到内部治理`

### `/demo`

已确认页面 Hero 口径已经同步：

- `让每一次回答，都成为下一次的能力。`

## 6. 当前能下的结论

这轮验证能支持以下判断：

- 默认样本已切换正确
- 页面信息架构已收敛
- 页面口径已统一
- `/workspace` 首次进入后，按代码逻辑会自动预载入默认样本
- 样本模式与上传模式的状态机逻辑已就位

## 7. 当前仍未替代的真实人工验证

由于环境限制，以下项目仍建议在真实浏览器里补做：

1. 首次进入 `/workspace` 时，默认样本是否真的已渲染到输入框与文件区
2. 点击“上传自己的文件”后，按钮文案和模式提示是否如预期变化
3. 切回“推荐样本”后，是否能稳定恢复样本材料
4. 详情区折叠项在真实浏览器中的交互是否顺手

## 8. 一句话结论

在没有浏览器自动化的前提下，当前 V1 的页面入口、默认样本和前端状态机已经基本对齐；

剩下最值得补的一步，是用真实浏览器再走一遍点击流。
