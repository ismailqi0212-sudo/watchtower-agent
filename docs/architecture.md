# Architecture

## 1. Goal and non-goals

**Goal:** a single-user, evidence-bound watchlist review agent that can run offline, explain every conclusion, and be evaluated.

**Non-goals:** real-time trading, order execution, multi-tenant SaaS, full fundamental coverage, multi-agent orchestration.

The project is deliberately a *vertical slice*: enough product surface to demo, enough engineering to discuss reliability.

---

## 2. Components

```text
┌─────────────────────────────────────────────────────────────┐
│ React 19 + HeroUI v3 workspace                              │
│  Watchlist + preview   Run card   Evals                     │
└───────────────┬─────────────────────────────────────────────┘
                │ /api/*
┌───────────────▼─────────────────────────────────────────────┐
│ FastAPI                                                     │
│  api.py: validation, HTTP errors, static SPA hosting        │
└───────────────┬─────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────┐
│ AnalysisService                                             │
│  seed / add / analyze / get_run / chat                      │
│  persistence: runs, tool_calls, reports, chat_messages      │
└───────┬───────────────────────────────┬─────────────────────┘
        │                               │
┌───────▼──────────────┐       ┌────────▼────────────────────┐
│ AgentRunner          │       │ Evals                       │
│  demo policy         │       │  golden set                 │
│  LLM tool calling    │       │  point-in-time backtest     │
│  fallback            │       └────────┬────────────────────┘
└───────┬──────────────┘                │
        │                               │
┌───────▼──────────────┐       ┌────────▼────────────────────┐
│ ToolRegistry (6)     │       │ SQLite                      │
│  quote/history/ind   │       │  stocks/runs/tool_calls     │
│  news/fund/benchmark │       │  reports/chat_messages      │
└───────┬──────────────┘       └─────────────────────────────┘
        │
┌───────▼──────────────────────┐
│ Provider factory             │
│  DemoProvider (fixtures)     │
│  AkshareProvider (A-share)   │
│  NasdaqProvider (US)         │
│  YFinanceProvider (fallback) │
│  TavilyNewsProvider (news)   │
└──────────────────────────────┘
```

Key rule: **the agent never talks to a vendor SDK directly.** It only sees the tool contract. Swapping data vendors is a provider-level change.

---

## 3. UI composition

The workspace is a single-screen, master-detail shell:

- left rail: brand, add action, search, watchlist, connection state;
- top bar: two-tab navigation (复盘 / 评测), mode chip, API link;
- watchlist: dense table with a right-side preview of the selected stock;
- report: header + three tabs (决策 / 证据 / 执行) + persistent chat rail;
- evaluation: metric strip + two independently scrollable tables.

HeroUI v3 supplies Button, Input, Table, Tabs, Chip, Drawer, Alert, Spinner and Skeleton. Tailwind v4 handles layout; the theme overrides HeroUI tokens to a near-black palette and thin type.

## 4. Data model

| Table | Purpose | Key fields |
|---|---|---|
| `stocks` | watchlist | `symbol`, `name`, `market`, `industry` |
| `runs` | one analysis execution | `id`, `symbol`, `status`, `mode`, `model`, `latency_ms`, tokens, cost |
| `tool_calls` | replayable trace | `run_id`, `step`, `kind`, `tool`, `args_json`, `result_json`, `ok`, `latency_ms` |
| `reports` | structured decision card | `run_id`, `action`, `score`, `confidence`, `data_quality`, `payload_json`, `markdown` |
| `chat_messages` | follow-up Q&A | `run_id`, `role`, `content` |

SQLite is enough for a single user. WAL is enabled; the schema is created idempotently at startup.

---

## 5. Agent sequence

1. `AnalysisService.analyze(symbol)` resolves the stock and freezes `as_of` (latest available bar).
2. Creates a `run` row with mode/model.
3. `AgentRunner`:
   - demo mode: fixed but explicit tool order, 6 calls;
   - LLM mode: model chooses tools, up to `AGENT_MAX_STEPS`.
4. Every tool returns:
   ```json
   {
     "ok": true,
     "data": {},
     "evidence": [{"id": "...", "kind": "...", "summary": "...", "payload": {}}],
     "data_quality": "ok",
     "summary": "..."
   }
   ```
5. Synthesizer creates the report JSON.
6. `validate_and_repair` clamps and repairs:
   - score/action consistency;
   - plan ordering;
   - evidence existence;
   - date sanity;
   - confidence cap under partial data.
7. Persists report + trace, finishes the run.
8. UI loads run detail; evidence chips open raw payload; chat uses the stored report.

---

## 6. Evidence contract

Every evidence item has:

| Field | Meaning |
|---|---|
| `id` | stable identifier, e.g. `ind:600519:2026-10-28` |
| `kind` | `quote`, `history`, `indicator`, `news`, `fundamental`, `benchmark` |
| `label` | short human-readable source |
| `summary` | one-line fact |
| `as_of` | date of the fact |
| `payload` | raw values used to derive the claim |

Every `thesis`/`risk` item has `evidence_ids`. The validator removes ids that do not exist and attaches a relevant evidence item if the claim had none. The UI surfaces this as a clickable chip; a claim with no evidence is visibly flagged.

Why this matters: an LLM can write a plausible sentence; it cannot fabricate an evidence id that exists in the tool output unless the validator allows it. This is a cheap, deterministic defense against a large class of hallucinations.

---

## 7. Validation rules

| Rule | Action on violation |
|---|---|
| `0 <= score <= 100` | clamp |
| `action` in allowed enum | replace with score-derived action |
| action/score mismatch | repair to score band, except allowed hold/watch equivalence |
| `stop_loss < entry_low <= entry_high < target_price` | recompute from current price/MA |
| evidence id missing | drop, attach relevant evidence |
| `< 3` evidence items | `data_quality=partial`, confidence cap |
| report date > as_of | revert to as_of |
| `position_pct` outside 0–40 | clamp |

Repair is preferred over rejection: a run should still produce a usable, visibly degraded card.

---

## 8. Evaluation

### Golden set

`evals/golden_set.json` contains cases with:

- `required_tools`: tools that must be called;
- `expected_actions`: acceptable action set;
- `must_have_evidence_kinds`: evidence categories that must appear;
- `expect_partial_data`: optional data-quality expectation.

`evals/run_eval.py` computes tool coverage, schema validity, action accuracy, evidence coverage, latency, and per-case issues. It is a reporter, not a hard CI gate in the first version; CI can decide the threshold.

### Backtest

`evals/run_backtest.py` samples every 12th trading day after enough history for MA60, rebuilds the card using only data up to that day, and evaluates the next 5 trading days.

Definitions:

- bullish actions: `buy`, `add`;
- bearish actions: `reduce`, `sell`, `avoid`;
- neutral: `hold`, `watch` (evaluated with a ±2% band);
- directional hit rate excludes neutral;
- `always_long_hit_rate` is the fraction of all sampled dates with positive 5-day return, a simple baseline.

Known limitations:

- synthetic fixtures, not real market data;
- no transaction costs/slippage;
- current fundamentals withheld for historical dates to avoid look-ahead;
- small sample (54 signals), no statistical significance claim.

---

## 9. Replacing the data provider

`DATA_PROVIDER` selects `demo`, `akshare`, `nasdaq`, `yfinance`, or `auto` (A-share + US).  
`TAVILY_API_KEY` optionally adds Tavily news on top of the market provider.

The factory lives in `app/data/factory.py`; the real adapters live in
`app/data/akshare_provider.py`, `app/data/nasdaq_provider.py` and the optional `yfinance_provider.py`; `composite_provider.py` routes mixed watchlists.

Implement the same methods:

```python
list_stocks() -> list[dict]
resolve(raw: str) -> dict
get_quote(symbol, as_of) -> dict
get_history(symbol, days, as_of) -> list[dict]
get_news(symbol, days, as_of) -> {"items": [...], "data_quality": "ok|missing"}
get_fundamentals(symbol, as_of) -> {"data": {...}, "data_quality": "ok|partial|missing"}
get_benchmark(days, as_of) -> {"symbol": ..., "bars": [...], ...}
latest_date(symbol) -> str
```

Then change `create_app` / `AnalysisService` to inject the new provider. Keep `as_of` semantics: historical calls must not read future data.

---

## 10. Failure handling

| Failure | Behavior |
|---|---|
| Unknown symbol | 400 at API boundary, no run created |
| Tool exception | tool returns `ok=false`; report degrades |
| LLM timeout/error | fallback to demo policy, trace warning, run `partial` |
| LLM invalid JSON | fallback after step budget, trace warning |
| SQLite write failure | run marked failed, error stored |
| Frontend API down | visible error banner + retry |

The demo path is intentionally boring: it proves the product still works when the model is unavailable.

---

## 11. Scaling path

If this became a real product:

1. Add auth and per-user watchlists.
2. Replace fixtures with a real provider, add caching and rate-limit handling.
3. Add point-in-time fundamentals/announcements.
4. Move background analysis to a queue (Celery/RQ) and stream progress.
5. Add a notification channel and daily digest.
6. Expand golden set to 30–50 cases and add adversarial cases.
7. Add LLM cost/latency dashboards and model routing.

---

## 12. Research mode (P0)

The research mode is deliberately split from the review Agent:

```text
ResearchService
  ├── DocumentService -> PdfParser (PyMuPDF)
  └── MetricExtractor -> page + quote cells

AgentRunner (unchanged)
  └── ReviewProfile: six market tools
```

P0 does **not** add a second Agent loop and does **not** let an LLM invent numbers. The annual-report extractor produces cells only when the page text matches; missing cells remain `None` with `status="missing"`.

### Data flow

1. `POST /api/research/bootstrap` finds the four sample PDFs.
2. `PdfParser` stores page text, dimensions and hashes.
3. `extract_yanji_cloud_metrics` extracts financial and business metrics.
4. `ResearchService` builds a read model: `sources + metrics + quality`.
5. The React research page renders the worksheet; clicking a value opens `/api/documents/{id}/pages/{page}.png`.
6. `GET /api/documents/{id}/file` serves the original PDF.

### Why deterministic first

Business metrics such as ARPU/DAU are easy to misread. A model-assisted extractor can come later, but the first version must prove the citation path:

```text
cell -> document_id -> physical page -> quote -> rendered page
```

The next step is a `ResearchProfile` that reuses the same `AgentRunner` and `ToolRegistry`, adding document tools (`search_filings`, `read_filing_page`, `get_metric_series`) without adding a new loop.

---

## 12. Research mode (P0)

The research mode is deliberately split from the review Agent:

```text
ResearchService
  ├── DocumentService -> PdfParser (PyMuPDF)
  └── MetricExtractor -> page + quote cells

AgentRunner (unchanged)
  └── ReviewProfile: six market tools
```

P0 does **not** add a second Agent loop and does **not** let an LLM invent numbers. The annual-report extractor produces cells only when the page text matches; missing cells remain `None` with `status="missing"`.

### Data flow

1. `POST /api/research/bootstrap` finds the four sample PDFs.
2. `PdfParser` stores page text, dimensions and hashes.
3. `extract_yanji_cloud_metrics` extracts financial and business metrics.
4. `ResearchService` builds a read model: `sources + metrics + quality`.
5. The React research page renders the worksheet; clicking a value opens `/api/documents/{id}/pages/{page}.png`.
6. `GET /api/documents/{id}/file` serves the original PDF.

### Why deterministic first

Business metrics such as ARPU/DAU are easy to misread. A model-assisted extractor can come later, but the first version must prove the citation path:

```text
cell -> document_id -> physical page -> quote -> rendered page
```

The next step is a `ResearchProfile` that reuses the same `AgentRunner` and `ToolRegistry`, adding document tools (`search_filings`, `read_filing_page`, `get_metric_series`) without adding a new loop.
