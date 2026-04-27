# H3 PDF 无规则发现路径 Query

## 推荐 Query

```text
请根据材料给出处理建议。
```

## 适用材料

- 使用当前那份 H3 研报 PDF：
  `H3_AP202604031821011697_1.pdf`

## 推荐使用方式

为了尽量去掉场景识别的不确定性，建议这样用

1. 打开 `/workspace`
2. 上传 `H3_AP202604031821011697_1.pdf`
3. 场景固定为 `equity_research`
4. 输入这条 query：

```text
请根据材料给出处理建议。
```

## 为什么这条会走无规则发现

在**当前代码版本**下，这条 query 会把系统带到：

```text
route_decision = exploration
failure_reason = no_direct_or_composable_rule
```

原因不是“完全没有命中任何规则”，而是：

- 它会被 `equity_research.full_analysis.v1` 弱命中
  原因：
  query 里有“建议”这个词，会命中 full analysis 的 `query_signals`
- 但当前这份 H3 PDF 的已知解析状态是：
  - `analyst_rating`：grounded
  - `key_risks`：grounded
  - `target_price`：missing
- 所以 `full_analysis` 最终是：
  - `binding_status = partially_bindable`
  - 不能进入 `direct_match`
- 同时又没有可组合的 atomic 路径能接住
- 按当前 `runtime_core/compiler.py` 的路由逻辑，最后会落到：
  - `exploration`

## 本地验证结果

我已经按当前系统的 retrieval + binding + compiler 逻辑做过验证，结果是：

```python
{
  'route_decision': 'exploration',
  'selected_rule_id': None,
  'composition_plan': None,
  'failure_reason': 'no_direct_or_composable_rule',
  'missing_slots': []
}
```

同时关键候选规则状态是：

- `equity_research.full_analysis.v1`
  - `binding_status = partially_bindable`
  - `eligible_for_direct_match = True`
  - `missing_slots = ['target_price']`
- 其他 `rating / target_price / key_risks / risk_count` 规则
  - 都没有形成可直接执行路径

## 为什么不用别的问法

像这些问法都**不适合**拿来保证走无规则发现：

- “2025年工商银行的整体业绩表现如何？”
- “该报告识别了哪些潜在的投资风险？”
- “这份研报对工商银行的投资评级是什么？”
- “目标价是多少？”

因为这些都落在当前 `equity_research` 规则覆盖范围内，很容易走：

- `direct_match`
  或
- `rule_composable`

## 注意

这里说的“稳定走无规则发现”，是指：

- **基于当前这份 H3 PDF**
- **基于当前这套规则库**
- **基于当前这版代码**

如果后面你把：

- `target_price` 的解析补齐了
- 或者新增了一条“泛化建议类”研报规则

那这条 query 就不一定还会走 `exploration`。

## 一句话结论

如果你现在想用同一份 H3 研报 PDF，稳定演示“无规则发现”路径，当前最合适的 query 就是：

```text
请根据材料给出处理建议。
```
