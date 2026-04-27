# Demo Cases

这个目录用于组织当前系统能力展示数据。

## 目录结构

- `workspace/`: 面向 `/workspace` 的案例
- `prototype/`: 面向 `/prototype` 的案例

每个 case 目录统一包含：

- `materials/`
- `input.json`
- `expected.json`
- `notes.md`

当前只生成目录骨架和预期说明，真实材料文件后续补到 `materials/`。

## 当前状态

第一批模拟材料已经补到部分 `workspace` case 的 `materials/` 目录里，可直接用于本地跑通链路。

当前已补模拟材料的 `workspace` case：

- `fund_docx_direct_warn`
- `credit_docx_direct_no_notice`
- `credit_docx_direct_notify`
- `fund_pdf_direct_warn`
- `credit_xlsx_direct_notify`
- `mixed_html_xlsx_fact_merge`
- `broken_pdf_plus_txt`
- `direct_match_patch_evidence`
- `workspace_known_family_patch_scope`

其中：

- `workspace_exploration_new_atomic` 本来就是“无材料进入 exploration”的样本，保持空目录。
- `prototype/*` 使用系统内置 `sim_data` 与 flow，不依赖 `materials/` 目录里的外部文件。

## 运行方式

直接运行某个案例：

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn
```

按 `expected.json` 只检查关键字段：

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn --check-expected
```
