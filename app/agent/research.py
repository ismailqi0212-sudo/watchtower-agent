"""Research profile: one AgentLoop, document tools, evidence-bound answers.

This module reuses ``_run_model_tool_loop`` from the review runner. It does not
create a second loop and it does not parse PDFs; all document access goes
through ResearchService/DocumentService.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agent.runner import _estimate_cost, _extract_json, _run_model_tool_loop, _trace
from app.agent.tools import ToolContext, ToolRegistry, ToolSpec, _envelope
from app.config import Settings


RESEARCH_SYSTEM_PROMPT = """你是 Watchtower 的研究 Agent。你的任务是使用可用数据（在线行情、技术指标、新闻、基本面、上传材料）回答用户问题，并让每个数字都有来源。

工作规则：
1. 先调用 get_research_overview 了解已有指标、年份和材料。
2. 需要年报数值时调用 get_metric_series；需要解释原因时调用 search_filings / read_filing_page。
3. 没有 PDF 材料时，直接使用行情/技术指标/新闻/基本面工具回答；不要假装读过财报。
4. 回答“这家公司怎么样”这类问题时，先取行情、指标、新闻和基本面，再说明证据边界。
5. 只使用工具返回的数据。不要自己补数字，不要用常识替代数据源。
6. 每个结论都必须引用 citations 中的 evidence；evidence 必须来自工具返回结果。
7. 缺失数据要写进 gaps，不要补零，不要把“未披露”说成“下降”。
8. 禁止用收入、会员收入或其他指标反推未披露的付费用户、ARPU、DAU；缺失就说明缺失，不给出替代推算值。
9. 只允许对已披露数字做简单同比、占比或差值，并标注“计算值”；不要引入工具之外的年份或数字。
10. answer 正文不要出现 evidence id、doc:... 或工具名。
11. 为了让正文数据可点击：在每处含数字或事实的句子后加 [[n]]，n 是 citations 数组中的序号（从 1 开始）；citations 按正文首次出现顺序排列。
12. 区分事实与判断；原因是假设时要明确说“需要进一步核对”。
13. 最终只输出一个 JSON 对象，不要 Markdown 代码块或额外解释。

输出 JSON：
{
  "answer": "给用户的研究回答，可用换行",
  "citations": ["doc:...:p7:online_paying_users:2023"],
  "artifacts": [
    {"kind": "metric_table", "title": "2021–2024 经营数据", "metric_keys": ["revenue", "online_paying_users"]}
  ],
  "gaps": ["2024 年报未披露用户指标"]
}
"""


@dataclass
class ResearchResult:
    answer: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    generated_by: str = "demo-research"
    error: Optional[str] = None


def _detail(ctx: ToolContext) -> Dict[str, Any]:
    if not ctx.research or not ctx.session_id:
        raise ValueError("research session is not configured")
    detail = ctx.research.get_session(ctx.session_id)
    if not detail:
        raise ValueError("research session not found")
    return detail


def _metric_evidence(row: Dict[str, Any], period: str) -> Optional[Dict[str, Any]]:
    cell = row.get("cells", {}).get(period) or {}
    if cell.get("value") is None or not cell.get("document_id") or not cell.get("page"):
        return None
    quote = cell.get("quote", "")
    return {
        "id": f"doc:{cell['document_id']}:p{cell['page']}:{row['key']}:{period}",
        "kind": "document",
        "label": f"{row['label']} · {period}",
        "summary": f"{row['label']} {cell['value']} {row.get('unit', '')}".strip(),
        "as_of": period,
        "payload": {
            "document_id": cell["document_id"],
            "page": cell["page"],
            "quote": quote,
            "metric_key": row["key"],
            "period": period,
        },
    }


def _overview(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    detail = _detail(ctx)
    rows = []
    evidence = []
    for row in detail["metrics"]:
        rows.append(
            {
                "key": row["key"],
                "label": row["label"],
                "unit": row["unit"],
                "values": {
                    period: cell.get("value")
                    for period, cell in row["cells"].items()
                    if cell.get("value") is not None
                },
                "missing": row.get("missing", []),
            }
        )
        for period in detail["periods"]:
            item = _metric_evidence(row, period)
            if item:
                evidence.append(item)
    return _envelope(
        {
            "session_id": detail["id"],
            "name": detail["name"],
            "symbol": detail["symbol"],
            "periods": detail["periods"],
            "documents": [
                {"id": source["id"], "name": source["name"], "year": source.get("year")}
                for source in detail["sources"]
            ],
            "metrics": rows,
            "candidates": [
                {"label": row["label"], "unit": row["unit"], "periods": row.get("periods", [])}
                for row in detail.get("candidates", [])[:12]
            ],
            "quality": detail["quality"],
        },
        evidence,
        f"{detail['name']}：{len(detail['sources'])} 份年报，{detail['quality']['available_cells']}/{detail['quality']['expected_cells']} 个指标单元可用，{len(detail.get('candidates', []))} 组候选待确认。",
        quality="ok" if detail["quality"]["missing_cells"] == 0 else "partial",
    )


def _metric_series(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    detail = _detail(ctx)
    key = str(args.get("metric_key") or "").strip()
    if not key:
        return _overview(ctx, args)
    row = next((item for item in detail["metrics"] if item["key"] == key), None)
    if not row:
        return _envelope(
            {"available": [item["key"] for item in detail["metrics"]]},
            [],
            f"没有指标 {key}。",
            quality="missing",
            ok=False,
            error="unknown metric",
        )
    evidence = []
    values = {}
    for period in detail["periods"]:
        cell = row["cells"].get(period, {})
        values[period] = cell.get("value")
        item = _metric_evidence(row, period)
        if item:
            evidence.append(item)
    missing = [period for period, value in values.items() if value is None]
    return _envelope(
        {
            "metric_key": row["key"],
            "label": row["label"],
            "unit": row["unit"],
            "periods": detail["periods"],
            "values": values,
            "missing": missing,
        },
        evidence,
        f"{row['label']}：" + " / ".join(
            f"{period} {values[period]}" if values[period] is not None else f"{period} 未披露"
            for period in detail["periods"]
        ),
        quality="partial" if missing else "ok",
    )


def _search_filings(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    detail = _detail(ctx)
    query = str(args.get("query") or "").strip()
    if not query:
        return _envelope({}, [], "缺少检索词。", quality="missing", ok=False, error="empty query")
    wanted = str(args.get("document_id") or "").strip()
    evidence = []
    hits = []
    for source in detail["sources"]:
        if wanted and source["id"] != wanted:
            continue
        for hit in ctx.research.documents.search(source["id"], query, limit=4):
            page = hit["page"]
            evidence.append(
                {
                    "id": f"doc:{source['id']}:p{page}:search:{len(evidence)}",
                    "kind": "document",
                    "label": f"{source['name']} · p{page}",
                    "summary": hit["text"][:120],
                    "as_of": str(source.get("year") or ""),
                    "payload": {
                        "document_id": source["id"],
                        "page": page,
                        "quote": hit["text"][:500],
                        "query": query,
                    },
                }
            )
            hits.append(
                {
                    "document_id": source["id"],
                    "document_name": source["name"],
                    "page": page,
                    "text": hit["text"][:800],
                }
            )
    return _envelope(
        {"query": query, "hits": hits},
        evidence,
        f"检索“{query}”，命中 {len(hits)} 个页面。",
        quality="ok" if hits else "missing",
    )


def _read_page(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    detail = _detail(ctx)
    document_id = str(args.get("document_id") or "").strip()
    page = int(args.get("page") or 0)
    source = next((item for item in detail["sources"] if item["id"] == document_id), None)
    if not source or page < 1:
        return _envelope({}, [], "文档或页码无效。", quality="missing", ok=False, error="invalid page")
    page_data = ctx.research.documents.db.get_document_page(document_id, page)
    if not page_data:
        return _envelope({}, [], "页面不存在。", quality="missing", ok=False, error="page not found")
    text = page_data.get("text", "")
    evidence = [
        {
            "id": f"doc:{document_id}:p{page}:read",
            "kind": "document",
            "label": f"{source['name']} · p{page}",
            "summary": text[:120],
            "as_of": str(source.get("year") or ""),
            "payload": {
                "document_id": document_id,
                "page": page,
                "quote": text[:800],
            },
        }
    ]
    return _envelope(
        {
            "document_id": document_id,
            "document_name": source["name"],
            "page": page,
            "text": text[:4000],
        },
        evidence,
        f"读取 {source['name']} 第 {page} 页，{len(text)} 字符。",
    )


def build_research_tools() -> Dict[str, ToolSpec]:
    return {
        "get_research_overview": ToolSpec(
            name="get_research_overview",
            description="获取当前研究会话的年报、年份、指标表和缺口。回答前先调用。",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_overview,
        ),
        "get_metric_series": ToolSpec(
            name="get_metric_series",
            description="获取某个经营指标的逐年值、缺失年份和 PDF 页码证据。",
            parameters={
                "type": "object",
                "properties": {
                    "metric_key": {
                        "type": "string",
                        "description": "指标 key，例如 revenue、online_paying_users、online_arpu",
                    }
                },
                "additionalProperties": False,
            },
            handler=_metric_series,
        ),
        "search_filings": ToolSpec(
            name="search_filings",
            description="在已上传年报中检索关键词，返回物理页和原文片段。",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "document_id": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_search_filings,
        ),
        "read_filing_page": ToolSpec(
            name="read_filing_page",
            description="读取某份年报的某一物理页。",
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "page": {"type": "integer", "minimum": 1},
                },
                "required": ["document_id", "page"],
                "additionalProperties": False,
            },
            handler=_read_page,
        ),
    }


def _fallback_answer(ctx: ToolContext) -> ResearchResult:
    detail = _detail(ctx)
    citations = []
    for row in detail["metrics"]:
        for period in detail["periods"]:
            item = _metric_evidence(row, period)
            if item and len(citations) < 8:
                citations.append(item)
    lines = [
        f"已读取 {len(detail['sources'])} 份年报，共 {detail['quality']['available_cells']}/{detail['quality']['expected_cells']} 个指标单元可用。",
        "",
    ]
    for row in detail["metrics"][:5]:
        values = [
            f"{period} {row['cells'][period]['value']}" if row['cells'][period]['value'] is not None else f"{period} 未披露"
            for period in detail["periods"]
        ]
        lines.append(f"- {row['label']}：" + " / ".join(values))
    lines += [
        "",
        "缺失数据不会被补零。点击引用可查看 PDF 物理页。",
    ]
    return ResearchResult(
        answer="\n".join(lines),
        citations=citations,
        artifacts=[
            {
                "kind": "metric_table",
                "title": "2021–2024 经营数据",
                "metric_keys": [row["key"] for row in detail["metrics"]],
            }
        ],
        gaps=[f"{row['label']} 2024 未披露" for row in detail["metrics"] if row.get("missing")],
        trace=[_trace(0, "plan", summary="LLM 不可用，使用确定性研究底稿回答。")],
        generated_by="demo-research",
    )


def run_research_agent(
    ctx: ToolContext,
    question: str,
    settings: Settings,
    history: Optional[List[Dict[str, Any]]] = None,
) -> ResearchResult:
    if not settings.llm_enabled:
        return _fallback_answer(ctx)

    from openai import OpenAI

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.agent_timeout_seconds,
    )
    detail = _detail(ctx)
    registry = ToolRegistry(build_research_tools())
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
    ]
    # Keep the last two turns for follow-up context. Tool messages are not
    # replayed; a fresh tool loop can re-read the authoritative data.
    for item in (history or [])[-4:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append(
        {
            "role": "user",
            "content": (
                f"研究标的：{detail['name']}（{detail['symbol']}）\n"
                f"可用年份：{', '.join(detail['periods'])}\n"
                f"材料：{len(detail['sources'])} 份年报\n"
                f"问题：{question}"
            ),
        }
    )
    trace = [_trace(0, "plan", summary="研究 Agent 规划：先看底稿，再按问题取指标或检索原文。")]
    loop = _run_model_tool_loop(client, settings, messages, registry, ctx, trace)
    content = loop["content"]
    parsed = _extract_json(content) if content else None
    if not parsed or not str(parsed.get("answer") or "").strip():
        fallback = _fallback_answer(ctx)
        fallback.trace = trace + fallback.trace
        fallback.error = "research model did not return valid JSON"
        return fallback

    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    for result in loop["results"].values():
        for item in result.get("evidence", []):
            evidence_by_id[item["id"]] = item
    citations = [evidence_by_id[item] for item in parsed.get("citations", []) if item in evidence_by_id]
    artifacts = [
        item
        for item in parsed.get("artifacts", [])
        if isinstance(item, dict) and item.get("kind") == "metric_table"
    ]
    trace.append(
        _trace(
            loop["step"],
            "final",
            result={"citations": len(citations), "answer_chars": len(str(parsed.get("answer") or ""))},
            summary=f"研究回答完成，引用 {len(citations)} 条证据。",
        )
    )
    answer = str(parsed.get("answer") or "").strip()
    answer = re.sub(r"\s*[\(（]doc:[^\)）]+[\)）]", "", answer).strip()
    return ResearchResult(
        answer=answer,
        citations=citations,
        artifacts=artifacts,
        gaps=[str(item) for item in parsed.get("gaps", []) if str(item).strip()],
        trace=trace,
        prompt_tokens=loop["prompt_tokens"],
        completion_tokens=loop["completion_tokens"],
        cost_usd=_estimate_cost(settings.llm_model, loop["prompt_tokens"], loop["completion_tokens"]),
        generated_by=f"llm:{settings.llm_model}",
    )
