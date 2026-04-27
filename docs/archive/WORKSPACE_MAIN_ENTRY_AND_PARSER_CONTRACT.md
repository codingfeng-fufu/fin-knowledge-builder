# /workspace 主入口与文档解析契约

## 1. 目标

这份文档只回答两件事：

1. 为什么 `/workspace` 要固定成当前系统主入口。
2. 在真实文档解析器尚未实现时，这条入口必须先遵守什么输入输出契约。

当前不讨论：
- 工程部署
- 多用户权限
- 真正的 PDF / Word / Excel 解析实现细节

## 2. 主入口定义

`/workspace` 的角色不是 demo 页面，也不是规则工厂后台。

它是：
- 专家工作台
- 问题与材料进入系统的统一入口
- runtime 与 Rule Factory 之间的前台承接层

主入口职责：
- 接收用户问题
- 接收上传材料
- 形成 Question Packet 与 Document Packet 预览
- 触发 runtime 生成建议
- 把结果、trace、feedback 继续送向 Rule Factory

## 3. 入口工作流

```text
/workspace
-> question_text + materials
-> document parser contract
-> question_packet / fact_sheet / evidence_packets
-> runtime route
-> answer + trace
-> feedback / Rule Factory
```

这里真正先要固定的是：
- 入口对象
- 输出对象
- 与 runtime 的桥接边界

而不是先把解析器实现完。

## 4. 当前 parser 契约

当前状态：
- `status = document_parser_mvp_connected`
- 当前已经支持文本、HTML、PDF、DOCX、XLSX 上传解析
- 更完整的结构化文档解析器后续补上

### 4.1 输入契约

必填：
- `question_text`

可选：
- `materials[]`

当前 `materials[]` 最小字段：
- `name`
- `content`

当前支持扩展名：
- `txt`
- `md`
- `json`
- `csv`
- `log`

目标支持扩展名：
- `pdf`
- `docx`
- `xlsx`
- `html`
- `msg`
- 以及现有文本类材料

### 4.2 目标输出契约

文档解析器未来必须稳定输出四层对象：

1. `document_set`
- `doc_id`
- `title`
- `doc_type`
- `source_type`
- `blocks`
- `parse_status`

2. `question_packet`
- `question_text`
- `scenario_hint`
- `question_type`
- `target_object`

3. `fact_sheet`
- `fact_id`
- `fact_type`
- `value`
- `evidence_refs`

4. `evidence_packets`
- `doc_id`
- `snippet_id`
- `text`
- `locator`

## 5. 为什么这条契约重要

没有这条契约，`/workspace` 只会是一个临时页面。

有了这条契约后：
- 前台入口先稳定下来
- runtime 的输入边界先稳定下来
- parser 本体后续可以独立替换
- Rule Factory 不会和前台输入层继续耦合

## 6. 当前 TODO

当前明确保留为 TODO 的内容：
- PDF / Word / Excel 解析器
- blocks / tables / layout locator
- parser 输出正式接入 `QuestionStruct / facts / evidence_refs`
- 更完整的工作台审阅与反馈界面

## 7. 一句话结论

当前阶段应该把 `/workspace` 看成：

**唯一主入口 + 已接入 document parser MVP + 待补更完整的结构化文档解析器。**
