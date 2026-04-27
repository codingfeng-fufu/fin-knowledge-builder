# V1 上线清单

> 目标：把当前收敛后的 V1 定义，转换成一份可执行、可勾选、可复核的上线 checklist。
> 适用版本：金融文档求解工作台 V1

## 1. 上线目标

本次 V1 不是发布“完整规则资产平台”，而是发布：

**一个由规则资产平台支撑的、带证据的金融文档求解工作台。**

上线时，用户应该明确感知到的价值只有三件事：

- 能拿到答案
- 能看到依据
- 当答不稳时，系统会明确给出状态

## 2. 本次上线的核心口径

### Hero 口径

- [x] 主标题：**让每一次回答，都成为下一次的能力**
- [x] 副标题：**把答案变成规则，把规则变成系统持续进化的起点。**

### 产品定义

- [x] 对外定义统一为“金融文档求解工作台”
- [x] 内部能力层仍保留“规则资产平台”定位
- [x] `/workspace` 定义为主入口
- [x] `/workflow` 定义为说明页
- [x] `/ops` 定义为内部治理页

## 2.1 最新执行结果（2026-04-15）

对应报告：

- `V1_REGRESSION_REPORT_2026-04-15.md`

当前回归结论：

- [x] `direct-match（fund_docx_direct_warn）`
- [x] `direct-match（credit_docx_direct_notify）`
- [x] `exploration -> draft/review`
- [x] `review -> publish`

当前最主要阻塞：

- 已定位并修复 `credit_docx_direct_notify` 的样本缺料问题。

这意味着：

- 当前 V1 的 default path 已经基本可用
- `fund_nav_warning` 与 `credit_notice` 两个 direct-match 场景都已有通过样本

## 3. 页面与交互上线检查

### 3.1 `/workspace`

- [x] Hero 已切到统一口径
- [x] 首屏只保留主任务相关信息
- [x] 左侧已拆成两条起步路径：
  - [x] 直接体验推荐样本
  - [x] 上传自己的文件
- [x] 推荐样本可直接运行，不要求用户再手动上传演示文件
- [x] 上传模式下，未选文件不会误触发运行
- [x] 首屏结构已收敛为：
  - [x] 开始方式
  - [x] 最终建议
  - [x] 结果概览
  - [x] 关键证据
- [x] “执行详情” 已改成用户导向标签：
  - [x] 判断依据
  - [x] 状态说明
  - [x] 内部记录
- [x] “内部记录” 已折叠，不再默认把方法草稿/求解过程平铺给用户
- [x] “相关问题” 已降级成样本区的轻量辅助项

### 3.2 `/workflow`

- [x] 页面口径已从“解法形成”改成“系统说明”
- [x] 明确不是主产品入口
- [x] 页面叙事已对齐“已有方法 / 进入内部处理”

### 3.3 `/ops`

- [x] 页面口径已从“方法沉淀”改成“内部治理”
- [x] 明确这是内部后台，不是普通用户入口
- [x] 保留 review / publish / rollback / version 能力

## 4. 默认体验检查

- [x] 默认样本已切回 `workspace/fund_docx_direct_warn`
- [x] `demo.workspace_case.list` 返回的 `default_case_ref` 已改成 fund case
- [x] 推荐样本清单仍保留 equity research showcase，但不再作为默认第一印象
- [ ] 在浏览器中人工确认首次进入 `/workspace` 时，默认样本已自动预载入，且按钮文案/模式提示正确

补充记录：

- 已完成一轮 `live HTTP + API + 前端状态机源码` 的手工风格验证，见：
  - `V1_MANUAL_STYLE_VERIFICATION_2026-04-15.md`

当前可确认：

- [x] 四个核心入口标题与口径已统一
- [x] 默认样本 payload 正确
- [x] 从源码逻辑可确认首次进入会执行默认样本预载
- [x] 样本模式 / 上传模式状态机已存在且互斥

当前仍建议补的真实人工项：

- [ ] 在真实浏览器中再点一遍首次进入与模式切换

## 5. 功能回归清单

## 5.1 direct-match 路径

目标：

- 用户可以直接得到答案
- 系统给出关键证据
- 不应无故进入内部治理流程

建议回归 case：

- [x] `demo_cases/workspace/fund_docx_direct_warn`
- [x] `demo_cases/workspace/credit_docx_direct_notify`

关键断言：

- [x] `route_decision` 符合 direct-match 预期
- [x] `final_decision` 正确
- [x] `final_answer` 可读且可辩护
- [x] `evidence_refs` 非空
- [x] `asset_pipeline.auto_status = recorded_only`
- [x] 不生成 feedback / draft / review

## 5.2 exploration 路径

目标：

- 用户得到明确状态，而不是伪确定性答案
- 内部自动形成后续治理对象

建议回归 case：

- [x] `demo_cases/workspace/workspace_known_family_patch_scope`
- [x] `demo_cases/workspace/workspace_exploration_new_atomic`

关键断言：

- [x] `route_decision = exploration`
- [x] `final_decision = needs_review`
- [x] 用户侧文案明确落在“进入内部处理/人工复核”
- [x] 自动生成 feedback
- [x] 自动生成 draft
- [x] 自动生成 review

## 5.3 审核发布路径

目标：

- exploration 产物可以进入内部治理闭环

关键断言：

- [x] `factory.review.approve` 后 review 状态更新为 `approved`
- [x] draft 状态更新为 `published`
- [x] `factory.rule_version.list` 中可见新 version
- [x] published version 能在 retrieval 资产视图中被看见

## 6. 文案与语言统一检查

- [x] 已新增 `PRODUCT_LANGUAGE_GUIDE.md`
- [x] `路径` 在主用户页面已尽量收敛为 `处理方式`
- [x] `答案来源` 已收敛为 `结果来源`
- [x] `exploration` 在主用户页面已表达为 `进入内部处理`
- [x] `方法沉淀` 已从主入口口径移到内部页口径
- [x] 再做一轮全站词汇搜索，确认没有明显残留：
  - [x] `方法沉淀`
  - [x] `解法形成`
  - [x] `路径`
  - [x] `答案引擎`
  - [x] `同意接入方法库`

## 7. 测试与技术检查

已验证：

- [x] `phase1_runtime.tests.test_demo_case_service`
- [x] `Phase1ApiServiceTests.test_handle_request_demo_workspace_case_actions`
- [x] `Phase1ApiServiceTests.test_handle_request_prototype_flow_run`
- [x] `Phase1ApiServiceTests.test_handle_request_product_workspace_solve_binary_docx`
- [x] `node --check phase1_runtime/static/app-core.js`
- [x] `node --check phase1_runtime/static/workspace-app.js`
- [x] `node --check phase1_runtime/static/workspace-renderers.js`

上线前还应补做：

- [x] 再跑一轮与 `workspace` 直接相关的最小回归集
- [x] 用干净端口启动服务，手工验证 `/workspace / workflow / ops / demo`
- [ ] 检查推荐样本模式与上传模式切换是否有边界 bug

## 8. 观测指标

上线后第一批重点观察：

### 用户侧

- [ ] 可用答案率
- [ ] 需要补充材料率
- [ ] 需要人工复核率
- [ ] 首次可辩护答案耗时

### 平台侧

- [ ] exploration 自动形成 review 的比例
- [ ] 审核通过率
- [ ] 发布版本数
- [ ] 被回滚版本数

### 行为侧

- [ ] 推荐样本启动占比
- [ ] 上传模式启动占比
- [ ] 首次访问后是否真正点击运行

## 9. 风险清单

- [x] `equity_research` 默认样本链路仍然比 fund case 更重，不能作为 V1 主体验
- [x] 部分 direct-match 场景对当前解析链仍有依赖，关闭相关能力后可能退化为 `needs_review`
- [x] 历史主库可能污染某些测试预期，涉及 publish/version 的测试应优先用临时库
- [x] 旧服务端口可能残留旧进程，手工验证时要避免误连旧实例

## 10. 上线判定门槛

满足以下条件才建议上线：

- [ ] `/workspace` 首次体验稳定
- [x] 默认样本是 fund warning
- [x] direct-match 和 exploration 两条链都至少手工走通一遍
- [x] 内部治理链（review -> approve -> version）可用
- [x] 页面文案与当前真实行为一致
- [x] 没有明显把内部动作暴露给普通用户的残留

## 11. 负责人确认

### 产品

- [ ] 产品定义确认
- [ ] 文案确认
- [ ] 默认体验确认

### 前端

- [ ] 主入口信息架构确认
- [ ] 样本/上传双路径确认
- [ ] 详情区折叠结构确认

### 后端 / 平台

- [ ] direct-match 稳定性确认
- [ ] exploration 自动沉淀确认
- [ ] review / publish / version 确认

## 12. 一句话上线标准

如果用户第一次进入系统，能在不理解规则平台概念的前提下：

- 知道怎么开始
- 能拿到答案或明确状态
- 能看到关键依据

并且系统内部还能继续沉淀规则，

那这版 V1 才算真的可以上线。
