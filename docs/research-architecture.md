# 研究模式架构（P0 数据底稿 + P1 研究对话）

## 目标

把“年报 PDF → 逐年经营数据 → 页码原文”做成一个独立研究模式，同时不破坏现有复盘 Agent。

当前范围：P0 数据底稿和 PDF 阅读；P1 研究对话已接入。

暂不做：
- 跟踪
- 自动研报
- OCR
- 自动抓取公告

## 分层

```text
HTTP API
  └── ResearchService          应用层：会话、底稿读模型
        ├── DocumentService    文档层：上传、解析、页码、渲染
        │     └── PdfParser    PyMuPDF，无 LLM
        └── MetricExtractor    领域适配器：年报指标 → 带页码的 cell

Agent（下一阶段）
  └── ResearchProfile
        └── research tools → ResearchService / DocumentService
```

约束：

- `PdfParser` 不导入 Agent、数据库或 HTTP。
- `DocumentService` 不导入 Agent 或 FastAPI。
- `ResearchService` 不实现 Agent 循环。
- Agent 只能通过工具调用研究服务，不能直接读 PDF。
- 复盘 Agent 和未来研究 Agent 共用同一个 `AgentRunner`、`ToolRegistry`、`Evidence`、`Validator`，不新增第二个循环。

## 数据表

```text
documents
  id, symbol, name, year, path, page_count, sha256, created_at

document_pages
  document_id, page, text, width, height

research_sessions
  id, symbol, name, question, status, created_at, updated_at

research_documents
  session_id, document_id, year

research_metrics
  id, session_id, metric_key, label, unit, period, value,
  document_id, page, quote, status, created_at

research_cards
  id, session_id, kind, title, body, data_json, selected, created_at
```

## P0 指标

财务：收入、毛利、毛利率、净利润、经营现金流。

业务：在线音乐 MAU、在线音乐月付费用户、在线音乐 ARPU、社交娱乐月付费用户、社交娱乐 ARPU。

规则：

- 每个 cell 必须带 `document_id + page + quote`。
- 只从页面文本匹配，不从数字猜。
- 缺失保留 `value=null` / `status=missing`，不补零、不推算。
- 2024 年报没有披露用户指标表，因此 5 个业务 cell 显示“未披露”。

## API

```text
POST /api/research/bootstrap
GET  /api/research/sessions
GET  /api/research/sessions/{id}
GET  /api/documents/{id}/file
GET  /api/documents/{id}/pages/{page}.png
```

`bootstrap` 是 P0 的样例入口，幂等。后续上传接口可以复用同一读模型。

## 前端

```text
研究
├── 研究记录（按股票）
├── 材料（4 份 PDF）
├── 数据底稿（指标表 + 曲线 + 导出 CSV）
└── 原文与依据（右侧 PDF 物理页 + quote）
```

点击表格数值或曲线点：

1. 找到该 cell 的 `document_id + page`
2. 右侧渲染对应物理页 PNG
3. 下方显示 quote
4. 可打开原始 PDF

## 研究对话（已接）

`ResearchProfile` 复用 `AgentRunner._run_model_tool_loop`，没有第二个循环。

工具：

- `get_research_overview`
- `get_metric_series`
- `search_filings`
- `read_filing_page`

一次问答：

```text
用户问题
→ ResearchProfile
→ 工具取指标/检索原文
→ 最终 JSON：answer + citations + artifacts + gaps
→ research_messages 持久化
→ 右侧 PDF 跟随 citation
```

约束：

- 回答只引用工具返回的 evidence id。
- 禁止用收入反推未披露的用户/ARPU。
- 缺失数据进入 `gaps`，不补零。
- `artifacts` 里的 `metric_table` 复用指标底稿渲染。

## 股票维度与材料

- `POST /api/research/sessions`：按 symbol 获取/创建会话。
- `POST /api/research/sessions/{id}/documents`：上传 PDF，写入 `documents/document_pages`。
- `research_documents` 关联会话与材料；`research_messages` 保存问答。
- 决策卡右上角“研究”会带入 `symbol/name`，进入对应股票研究。
- 样例 09899 自动抽取指标；其他股票先使用 `search_filings/read_filing_page`，指标抽取器后续泛化。
- 没有年报也可以开始研究：ResearchProfile 同时注册行情、技术指标、新闻、基本面工具；但回答会明确标注“没有年报材料”，不会假装读过财报。
- 左栏只放对话；材料在右上角弹层，避免把材料树当成会话导航。

## 通用指标候选

任意 PDF 上传后，`MetricCandidateScanner` 只做“候选”，不直接写底稿：

```text
PDF tables
→ 找年份表头
→ 行标签 + 年份列数值
→ 单位/页码/row quote
→ research_candidates
→ 用户在“待确认指标”中勾选
→ POST /metrics/confirm
→ research_metrics
```

规则：

- 候选表必须显示页码和 quote。
- 只扫描有年份表头的表格；没有表头的正文不硬猜。
- 用户确认前，数据底稿不增加任何数字。
- 样例 09899 继续使用精确指标适配器，避免被通用扫描覆盖。

## 研报组装

研报采用**片段制**，不再区分“指标底稿 / 研究结论”两个选择区：

- 对话正文：鼠标选中文字 → 浮出“加入研报”
- 表格 / 市场快照：右上角“加入研报”
- 不默认选中任何内容
- 已选片段按选择顺序进入报告

`ResearchReportService` 以片段为输入，先让 LLM 写成连贯研报；LLM 不通过数字/引用检查时回退确定性组装。两种路径都不重新查数据：

```text
已确认指标 + 已保存研究回答
→ sections：核心结论 / 经营数据 / 数据观察 / 风险与待核实 / 数据来源
→ research_reports
→ review：来源数、引用数、缺失数
→ Markdown
```

原则：

- 指标表只使用 `research_metrics`。
- 文本片段只使用用户选中的原文。
- LLM 正文必须带 `[[n]]` 内联引用；正文中不能引入片段外数字，否则回退确定性组装。
- 表格单元格直接绑定来源，点击打开右侧来源/PDF。
- 在线引用保留完整 payload；PDF 引用保留 `document_id + page + quote`。
- 缺失数据继续显示“未披露”。
- 两种模板：`brief` / `full`。

## 版本与润色

- `research_report_versions` 保存每次生成/保存的快照。
- `PUT /reports/{id}`：人工编辑标题、文本、缺口，生成新版本。
- `POST /reports/{id}/versions/{version}/restore`：恢复旧版本，生成新版本而不是覆盖历史。
- `POST /reports/{id}/polish`：只润色“数据观察”一节；一次文本 completion，不新增 AgentLoop。
- 润色数字护栏：输出中的每个数字必须能在润色输入中找到，或与输入数字在 0.5% 内；否则拒绝写入。
- 指标表、来源和引用不由润色修改。

## 下一阶段

1. 按股票归档研究 session，只显示当前股票历史。
2. 研报：卡片 → 选择 → 组装 → 引用核对 → Markdown。
3. 通用 PDF 上传和抽取器（当前是网易云音乐年报适配器）。
