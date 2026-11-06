# Interview notes

## 90-second pitch

> 我做了一个叫 Watchtower 的自选股复盘 Agent。它解决的不是“让模型写股评”，而是让模型的分析**可追溯、可校验、可回测**。
>
> 用户维护一个自选股列表，Agent 会调用 6 个工具拿行情、日线、技术指标、新闻、基本面和沪深300基准，然后生成一张决策卡：动作、评分、置信度、论点、风险、入场/止损/目标/仓位。
>
> 关键设计有三点。第一，**证据绑定**：每个论点必须带 evidence id，前端可以点开看原始数据，校验器会删掉不存在的引用。第二，**确定性护栏**：评分和动作必须一致，止损必须低于入场，目标必须高于入场，数据缺失会降级置信度。第三，**可评测**：8 条 golden set 检查工具选择、Schema 和证据覆盖；54 条历史信号做 point-in-time 回测，方向命中率 67%，对比“永远做多”基线 54%。
>
> 它默认不配 API Key 也能跑，因为有一个透明的 demo policy 作为 fallback 和 baseline；配了 Key 就切到 OpenAI-compatible tool calling。整个项目是 FastAPI + SQLite + React 19 + HeroUI v3，24 个测试，Docker 和 GitHub Actions 都能跑。真实数据层用 AKShare 接 A 股、Nasdaq 接美股、Tavily 补新闻。界面刻意做成单屏 master-detail：左侧窄自选股栏、中间列表/研究对话、右侧预览/PDF 原文；决策卡用三个 Tab 收住长内容。

---

## Why this project

- 它展示的是 **Agent reliability**，不是 prompt 技巧。
- 它有一个完整的 **产品闭环**：工作台 → 决策卡 → 追问 → 评测。
- 它有 **可量化的结果**，并且明确写了 baseline 和局限。
- 它刻意控制范围：一个市场、一个 Agent、三个页面。

---

## Key tradeoffs

### 1. Single agent, not multi-agent

**选择：** 单 Agent + 6 个工具 + 确定性校验器。

**理由：** 任务边界清晰，核心风险是工具选择、证据完整性、输出契约，而不是角色分工。多 Agent 会增加状态同步、成本、超时和调试复杂度，但不会自动提升结论质量。

**如果要做多 Agent：** 只加一个 critic，负责“证据覆盖 + 数字一致性”审查；不要一上来做 5 个角色。

### 2. Deterministic policy as fallback, not as the product

**选择：** demo-policy 与 LLM 共用工具和报告契约。

**理由：** 它让项目零配置可运行、可测试、可截图，也给 LLM 提供一个 baseline。LLM 失败时产品仍然能产出报告，而不是返回 500。

**代价：** demo 指标不能代表 LLM 质量；README 明确标注了这一点。

### 3. Evidence-bound output, not free-form text

**选择：** 结构化 JSON + `evidence_ids` + 校验器。

**理由：** 纯文本股评无法验证，也无法做 UI 交互。结构化输出让前端可以渲染证据抽屉、做回测、做筛选。

**代价：** Prompt 和 Schema 维护成本更高；小模型可能输出非法 JSON，所以需要 fallback。

### 4. SQLite + plain sqlite3, not Postgres/ORM

**选择：** 单文件数据库，schema 可见。

**理由：** 单用户、低并发、数据量小。面试时能直接讲清楚表结构和索引。

**代价：** 多用户/并发写入时需要迁移到 Postgres。

### 5. No RAG/vector DB

**选择：** 新闻按股票 + 日期过滤，取最近 N 条。

**理由：** 这个场景的检索条件非常结构化，不需要语义检索。上向量库会增加部署和解释成本，收益有限。

---

## Metrics to quote

From the current demo fixtures:

| Metric | Value | Note |
|---|---|---|
| Golden set pass | 8/8 | required tools + schema + evidence + action |
| Tool coverage | 100% | demo policy calls all 6 tools |
| Schema validity | 100% | Pydantic validation |
| Evidence coverage | 100% | each thesis has a real evidence id |
| Backtest directional hit | 67.4% | 54 signals, 5-day window |
| Always-long baseline | 53.7% | same sampled dates |
| Buy/Add avg 5d return | +3.0% | demo fixtures |
| Avg excess vs CSI300 | +1.5% | demo fixtures |
| P95 latency | 3ms | demo policy, no LLM |

**Say this out loud:** these are synthetic fixtures and a small sample; they validate the pipeline, not a trading edge.

---

## Likely questions

### “怎么防止大模型胡说？”

三层：

1. **工具白名单**：只能拿工具返回的数据，工具输出带 evidence id。
2. **输出契约**：Pydantic 校验 + 数值/日期/价格计划校验。
3. **证据绑定**：论点必须引用真实 evidence id；缺失时删除或降级，UI 可见。

剩余风险：模型可能“选择性引用”或做出错误推断。下一步是加 critic 和更多对抗样本。

### “为什么不用 LangChain/LangGraph？”

第一版刻意用原生 tool calling，循环只有一百多行，容易调试和讲清楚。框架不是护城河；等需要持久化状态、人工审批、复杂分支时再引入。

### “回测怎么做，怎么防未来函数？”

- 每个采样日只传 `as_of` 之前的数据；
- 新闻按日期过滤；
- 历史日期不注入当前基本面快照；
- 预测窗口固定 5 个交易日；
- 方向命中率排除 hold/watch，中性单独统计；
- 明确写出样本量、baseline、未计交易成本。

### “如果给你两周，你优先做什么？”

1. 接真实 A 股 provider（AkShare/Tushare），保持工具契约不变；
2. 把 golden set 扩到 30 条，加入缺数据/工具超时/新闻冲突；
3. 为 LLM 模式补成本/延迟/模型对比；
4. 加一个推送渠道和每日 artifact。

### “这个项目的护城河是什么？”

单点功能没有护城河。真正的积累是：工具契约、证据 schema、校验规则、评测集、失败案例库。这些让换模型、换数据源、换市场时仍然可控。

### “为什么 demo 的方向命中率比基线高？”

先承认：合成数据 + 小样本，不能外推。然后解释机制：demo policy 结合趋势、动量、量能、新闻和相对强弱，在趋势性合成的数据上更容易占优；真实市场需要更严格的 walk-forward 和成本模型。这个问题最好的回答是“我不把这个数字当结论”。

---

## Demo script (90 seconds)

1. 打开工作台：6 只自选股，最新价、走势、最近动作。
2. 点“运行分析”，进入决策卡。
3. 指出顶部：动作、评分、置信度、数据质量、耗时。
4. 指交易计划：入场、止损、目标、仓位。
5. 点一个证据 chip，打开原始 payload：“这句话来自这条指标/新闻”。
6. 展开一条 trace：“Agent 先调了什么、耗时多少、返回了什么”。
7. 在追问框问“止损位是多少”，展示多轮对话。
8. 打开评测台：golden set 和回测，指出 baseline。

---

## Resume bullets (fill real numbers)

> 独立设计并实现自选股复盘 Agent：6 个行情/指标/新闻工具、单 Agent 工具调用循环、Pydantic 结构化输出与 evidence id 证据绑定；支持无 Key 离线 demo 与 OpenAI-compatible LLM 双路径。

> 设计确定性校验器，覆盖评分/动作一致性、止损/目标价格序、证据存在性与日期检查；将非法报告修复为可用报告，并在 UI 中显式展示校验修正。

> 构建 8 条 golden set 与 54 条 point-in-time 历史信号回测，对比“永远做多”基线；demo fixtures 上方向命中率 67.4% vs 基线 53.7%，并明确标注样本与未来函数边界。

> 使用 FastAPI + SQLite + React 完成复盘、研究、评测与 run 详情四页工作台，24 个 pytest 覆盖指标、校验器、Agent、API 与评测；提供 Docker 与 GitHub Actions 每日任务。

---

## What I learned

- Agent 产品的难点不在“让模型调用工具”，而在**工具契约、失败降级、证据和评测**。
- 结构化输出不是万能药，必须配合确定性校验。
- 一个可解释的 baseline 比一个漂亮但无法复现的 demo 更有说服力。
- 范围控制是产品判断：三个页面、一个市场、一个 Agent，足够讲清楚故事。
