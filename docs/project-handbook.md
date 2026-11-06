# Watchtower 项目完整手册

> 一个盘后复盘 + 研究 + 研报的轻量 Agent 产品  
> 当前版本：2026-10-29  
> 代码：`watchtower-agent/`  
> 演示入口：<http://127.0.0.1:8765>

---

## 1. 一句话介绍

**Watchtower 把“自选股每天的复盘”和“围绕财报/在线数据的深度研究”串成一条可追溯的 Agent 工作流：**

```text
自选股复盘
→ 决策卡
→ 研究对话
→ 年报/在线数据
→ 选中片段
→ AI 研报
→ 编辑/版本
→ 质量评测
```

它不是荐股工具，也不是实时交易系统。  
它解决的是：**盘后怎么用一套可核对的流程，把数据变成结论和计划。**

---

## 2. 产品定位

### 2.1 对 C 端用户的价值

1. **省时间**
   - 不需要在行情软件、新闻、财报、Excel 之间来回切。
2. **强制证据**
   - 每个数字/结论都能回到来源；PDF 能回到物理页。
3. **把观点变成计划**
   - 有入场、止损、目标、仓位、失效条件，而不是“短期震荡”。
4. **建立复盘纪律**
   - 每天同一套流程，减少情绪化交易。
5. **研究可复用**
   - 对话、指标、研报版本都留在同一个股票上下文里。

### 2.2 不做什么

- 不做实时盘中信号
- 不接券商交易
- 不承诺收益
- 不把缺失数据补零/推算
- 不假装所有数据都来自年报

**年报只是材料之一。**  
所有数据都要有来源；PDF 只是其中一种可以展开成物理页的深度材料。

---

## 3. 用户旅程

```text
收盘后
  ↓
工作台：看自选股动作/评分
  ↓
决策卡：看计划、论点、风险、证据
  ↓
研究：问“为什么”，看年报/在线数据
  ↓
选中片段：文字选中 / 表格按钮
  ↓
研报：AI 写成文章，内联引用
  ↓
编辑/版本/AI 润色/导出
  ↓
评测：检查流程与历史信号
```

---

## 4. 总体架构

```text
React 19 + HeroUI v3
        │
        ▼
FastAPI
        │
        ├── AnalysisService（复盘）
        │      └── AgentRunner
        │            └── ReviewProfile
        │                  └── 6 个行情/资讯/基本面工具
        │
        ├── ResearchService（研究）
        │      ├── DocumentService
        │      │     └── PdfParser (PyMuPDF)
        │      ├── MetricExtractor（样例年报）
        │      └── AgentRunner
        │            └── ResearchProfile
        │                  ├── 行情/指标/新闻/基本面
        │                  └── 文档检索/读页/指标
        │
        └── ResearchReportService（研报）
               ├── 片段 → AI 写作
               ├── 数字/引用护栏
               ├── 版本历史
               └── Markdown 导出
```

核心原则：

- **一个 AgentLoop**
- **两个 Profile**
- **统一 Evidence / Validator / Trace**
- **报告是应用层组装，不是第二个 Agent**

---

## 5. Agent 架构

### 5.1 唯一的模型-工具循环

代码：`app/agent/runner.py`

```text
_run_model_tool_loop
  → 组装 messages
  → LLM chat.completions
  → 解析 tool_calls
  → ToolRegistry.execute
  → 工具结果回写 messages
  → 下一轮 / 返回最终文本
```

复盘和研究共用同一个循环，区别只在：

- system prompt
- 工具集
- 最终输出 schema
- 后处理/校验

### 5.2 ReviewProfile

复盘模式：

```text
get_quote
get_history
compute_indicators
search_news
get_fundamentals
get_benchmark
```

输出 `DecisionReport`：

- `action`
- `score`
- `confidence`
- `summary`
- `thesis[]`
- `risks[]`
- `plan`（entry/stop/target/position/horizon）
- `evidence[]`
- `validation_notes[]`

`app/agent/validator.py` 会修复/拒绝：

- 动作和评分不一致
- 止损/目标价格顺序错误
- 论点没有 evidence
- 日期/字段非法

### 5.3 ResearchProfile

研究模式：

```text
行情/技术指标/新闻/基本面/基准
+
get_research_overview
get_metric_series
search_filings
read_filing_page
```

特点：

- 没有 PDF 也能回答在线数据问题
- 有 PDF 时能检索原文、返回页码/quote
- 回答里带 `[[n]]` 内联引用
- citations 只保留工具真实返回的 evidence
- 缺失数据进入 gaps，不给替代推算

### 5.4 Trace

每一步记录：

```text
step / tool / args / result / ok / latency_ms / summary
```

前端「执行」Tab 可以回放。

### 5.5 降级

- LLM 超时/非法 JSON → 复盘走确定性 `run_demo_agent`
- 数据源失败 → 工具 `ok=false`，报告标 `partial/missing`
- 研报 AI 写作失败/数字越界 → 回退确定性组装

---

## 6. 数据层

### 6.1 Provider 抽象

代码：`app/data/`

```text
DemoProvider      合成 fixtures，离线可跑
AkshareProvider   A 股真实数据
NasdaqProvider    美股真实数据
YFinanceProvider  美股可选备用
TavilyNewsProvider 可选新闻
CompositeProvider 按代码路由 A 股/美股
```

`DATA_PROVIDER=auto` 时：

- 6 位数字代码 → A 股
- 字母 ticker → 美股

### 6.2 A 股

- 行情/日线：AKShare `stock_zh_a_hist`，失败切新浪、腾讯
- 新闻：东方财富 `stock_news_em`
- 财务：`stock_financial_abstract`
- 估值：`stock_zh_valuation_baidu`（PE/PB）
- 基准：沪深300 `stock_zh_index_daily('sh000300')`

### 6.3 美股

- 行情/日线/公司摘要：Nasdaq 公共接口
- 基准：SPY
- 备用：yfinance
- 新闻：Tavily（可选）

### 6.4 数据质量

- 返回 `ok=false` 不伪装成功
- `data_quality`: `ok / partial / stale / missing`
- 真实源失败不静默回退到合成数据

---

## 7. 复盘模式

### 7.1 决策卡

页面：

```text
自选股表 → 单股决策卡
```

三个 Tab：

- **决策**：结论、计划、论点、风险
- **证据**：每条论点对应的 evidence
- **执行**：工具调用 trace

### 7.2 计划

```json
{
  "entry_low": 1295,
  "entry_high": 1312,
  "stop_loss": 1262,
  "target_price": 1400,
  "position_pct": 20,
  "horizon": "5d"
}
```

计划是条件化的，不是“明天开盘买”。

### 7.3 证据

每条 evidence 包含：

- id
- kind
- label
- summary
- as_of
- payload

前端可以点开看原始字段。

### 7.4 追问

基于当前报告回答，不重新抓数据。

---

## 8. 研究模式

### 8.1 页面结构

```text
左栏：对话列表 + 新建研究
中间：对话 / 数据 / 研报
右侧：来源 / PDF 原文
```

材料不再占左栏；0 份材料时“材料”按钮自动隐藏。

### 8.2 新建研究

左栏 `+`：

- 从自选股选择
- 或输入代码 `AAPL / 600519 / 09899`
- 没有年报也能开始

### 8.3 在线数据

没有 PDF 时，ResearchProfile 仍然可以调用：

- 行情
- 技术指标
- 新闻
- 基本面
- 基准指数

回答会说明数据边界，不假装读过财报。

### 8.4 PDF 材料

`PdfParser` 使用 PyMuPDF：

- 解析页文本
- 保存页宽高
- 物理页渲染为 PNG
- 不承诺 OCR

样例 `data/uploads/2021.pdf … 2024.pdf`：

- 182 / 210 / 191 / 237 页
- 网易云音乐 2021–2024 年报

### 8.5 指标抽取

两种路径：

1. **样例精确适配器**
   - `app/documents/yanji.py`
   - 收入、毛利、毛利率、净利润、经营现金流
   - 在线音乐 MAU、付费用户、ARPU
   - 社交娱乐付费用户、ARPU

2. **通用候选扫描**
   - `app/documents/candidates.py`
   - 扫描有年份表头的表格
   - 生成候选，不直接写底稿
   - 用户确认后进入 `research_metrics`

### 8.6 数据来源

每个指标 cell：

```text
metric_key / label / unit / period
value
document_id
page
quote
```

前端：

- 对话正文：`[[n]]` 内联引用
- 表格：每个数值可点击
- 在线数据：右侧“数据来源”面板
- PDF：右侧物理页 + quote

### 8.7 选入研报

- 对话正文：选中文字 → 浮出“加入研报”
- 表格/市场快照：右上角按钮
- 不分类
- 不默认选中
- 片段按选择顺序进入研报

---

## 9. 研报模式

### 9.1 不是拼接，而是 AI 写作

```text
用户选中片段
+ 来源 catalog
+ 指标数据
→ LLM 写成连贯研报
→ 数字/引用校验
→ 章节
```

AI 输出 JSON：

```json
{
  "title": "研报标题",
  "sections": [
    {"title": "章节标题", "body": "正文，带 [[1]] 引用"}
  ]
}
```

### 9.2 数字护栏

- 正文数字必须在片段/来源中能找到（允许 0.5% 四舍五入）
- `[[n]]` 必须对应有效 citation
- 不通过 → 回退确定性组装

### 9.3 引用

- 内联 `[[n]]` → 前端渲染成可点击 `[n]`
- 点击 → 在线来源详情 / PDF 物理页
- 表格行带 `sources[period]`
- 不再堆底部“数据来源 N 条”标签

### 9.4 编辑与版本

- 编辑标题/正文/缺口
- 每次保存生成新版本
- 历史版本可查看/恢复
- AI 润色只改“数据观察”，新数字会被拒绝

### 9.5 导出

- Markdown
- 不做 PDF/Word（当前范围）

---

## 10. 评测

### 10.1 Golden Set

8 个固定场景，检查：

- 工具覆盖
- 证据覆盖
- Schema 合规
- 动作合理

### 10.2 历史回测

54 条固定信号，5 日窗口：

- 方向命中
- 永远做多基线
- 买入后 5 日均值
- 相对沪深300 超额
- 中性区间准确

### 10.3 定位

```text
流程质检，不是收益预测
固定 fixtures，结果可复现
不代表未来收益
```

---

## 11. 前端信息架构

```text
侧边栏：自选股总览 + 自选股列表
顶部：复盘 | 研究 | 评测

复盘：
  自选股表 + 右侧决策卡

研究：
  对话 / 数据 / 研报
  左栏会话
  右侧来源/PDF

评测：
  流程质检 + 历史信号
```

技术栈：

- React 19
- HeroUI v3
- Tailwind CSS v4
- Vite
- lucide-react

---

## 12. 数据模型

主要表：

```text
stocks
runs
tool_calls
reports
chat_messages

documents
document_pages
research_sessions
research_documents
research_metrics
research_candidates
research_messages
research_reports
research_report_versions
```

`research_metrics` 是研究底稿的事实来源；  
`research_reports` 只存组装结果和版本快照。

---

## 13. API

### 复盘

```text
GET  /api/health
GET  /api/stocks
POST /api/stocks
DELETE /api/stocks/{symbol}
POST /api/analyze
GET  /api/runs
GET  /api/runs/{id}
POST /api/chat
GET  /api/evals/latest
POST /api/evals/run
GET  /api/backtest/latest
POST /api/backtest/run
```

### 研究

```text
POST /api/research/bootstrap
POST /api/research/sessions
GET  /api/research/sessions
GET  /api/research/sessions/{id}
POST /api/research/sessions/{id}/documents
POST /api/research/sessions/{id}/ask
POST /api/research/sessions/{id}/metrics/confirm
GET  /api/research/sessions/{id}/reports
POST /api/research/sessions/{id}/reports
GET  /api/research/reports/{id}
PUT  /api/research/reports/{id}
GET  /api/research/reports/{id}/versions
GET  /api/research/reports/{id}/versions/{version}
POST /api/research/reports/{id}/versions/{version}/restore
POST /api/research/reports/{id}/polish
GET  /api/research/reports/{id}/markdown
GET  /api/documents/{id}/file
GET  /api/documents/{id}/pages/{page}.png
```

---

## 14. 启动与演示

### 14.1 启动

```bash
cd watchtower-agent
./scripts/start_demo.sh
```

Safari：

```bash
./scripts/start_demo_safari.sh
```

停止：

```bash
./scripts/stop_demo.sh
```

健康检查：

```bash
curl http://127.0.0.1:8765/api/health
```

### 14.2 10 分钟演示

| 时间 | 内容 | 关键话术 |
|---|---|---|
| 0:00 | 开场 | 盘后复盘 + 研究 Agent，不是荐股/实时系统 |
| 0:40 | 工作台 | A 股+美股、动作/评分筛选 |
| 1:40 | 决策卡 | 计划、证据、trace；不是一句“建议买入” |
| 4:00 | 研究 | 对话、无年报也能问、`[1]` 打开 PDF |
| 7:00 | 研报 | 片段 → AI 写作 → 内联引用 |
| 9:00 | 评测 | 流程质检 67% vs 54%，不是收益承诺 |
| 10:00 | 收尾 | 一个 Loop、两个 Profile、统一证据 |

完整话术见 `docs/demo-script.md`。

---

## 15. 当前边界

- 通用指标抽取目前以表格为主
- 不支持扫描件 OCR
- 样例年报抽取器是公司特定，不是任意 PDF 自动识别
- 研报导出只有 Markdown
- 评测是 fixtures，不是实盘回测
- 无登录/多用户/权限
- 不接交易

---

## 16. 面试 Q&A

### 这是投资建议吗？

> 不是。盘后决策辅助，不接交易，不构成投资建议。

### AI 会不会编数字？

> 指标抽取确定性；决策卡 validator；研报 AI 写作有数字/引用护栏，失败回退确定性组装。

### 为什么不用多 Agent？

> 单 Agent + Tool Registry 更可控、可调试、成本低；多 Agent 不是当前瓶颈。

### 67% 方向命中能说明赚钱吗？

> 不能。固定 fixtures 上的流程检查，不是实盘收益，样本也不够统计显著。

### 没有年报能研究吗？

> 能。在线行情/指标/新闻/基本面都能回答；只是没有 PDF 原文页。

### 数据源挂了怎么办？

> 工具返回失败，报告降级并标记数据质量，不静默用合成数据。

---

## 17. 一句话总结

> **复盘负责发现，研究负责解释，研报负责表达，评测负责证明流程没有跑偏。**

---

## 18. 工程状态

- 测试：**24 个 pytest**
- 前端：Vite 构建通过
- 健康检查：`status=ok`、`provider=multi`、`stocks=9`（以当前自选股为准）
- 启动：`./scripts/start_demo.sh`
- Safari：`./scripts/start_demo_safari.sh`
- 源码包：`watchtower-agent-src.zip`（不含 `.env`、PDF、数据库、日志）
