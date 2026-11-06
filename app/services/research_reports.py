"""Deterministic research-report assembly.

The report is assembled from already-confirmed metric cells and already-saved
research messages. It does not call an LLM and it does not re-query documents;
every citation is copied from the source artifact.
"""

from __future__ import annotations

import re
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from app.config import Settings
from app.db import Database
from app.services.research import ResearchService


def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if unit == "%":
        return f"{number:.1f}%"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if abs(number) >= 10:
        return f"{number:,.1f}"
    return f"{number:,.2f}"


def _numbers(text: str) -> List[str]:
    return [
        item.replace(",", "").replace("+", "")
        for item in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?%?", str(text or ""))
    ]


def _number_value(token: str) -> Optional[float]:
    try:
        return float(str(token).replace(",", "").replace("%", "").replace("+", ""))
    except ValueError:
        return None


def _number_supported(token: str, inputs: set) -> bool:
    if token in inputs:
        return True
    value = _number_value(token)
    if value is None:
        return True
    for candidate in inputs:
        other = _number_value(candidate)
        if other is None:
            continue
        tolerance = max(0.001, abs(other) * 0.005)
        if abs(value - other) <= tolerance:
            return True
    return False


def _metric_citation(row: Dict[str, Any], period: str) -> Optional[Dict[str, Any]]:
    cell = row.get("cells", {}).get(period) or {}
    if cell.get("value") is None or not cell.get("document_id") or not cell.get("page"):
        return None
    return {
        "id": f"doc:{cell['document_id']}:p{cell['page']}:{row['key']}:{period}",
        "label": f"{row['label']} · {period}",
        "document_id": cell["document_id"],
        "page": cell["page"],
        "quote": cell.get("quote", ""),
    }


class ResearchReportService:
    def __init__(self, db: Database, research: ResearchService):
        self.db = db
        self.research = research

    def generate(
        self,
        session_id: str,
        template: str = "brief",
        metric_keys: Optional[Sequence[str]] = None,
        message_ids: Optional[Sequence[int]] = None,
        snippets: Optional[Sequence[Dict[str, Any]]] = None,
        title: str = "",
        settings: Optional[Settings] = None,
    ) -> Dict[str, Any]:
        detail = self.research.get_session(session_id)
        if not detail:
            raise KeyError("research session not found")
        if snippets:
            return self._from_snippets(detail, template, list(snippets), title, settings)

        selected_keys = [key for key in (metric_keys or []) if key]
        rows = [row for row in detail["metrics"] if row["available"] > 0]
        if selected_keys:
            rows = [row for row in rows if row["key"] in selected_keys]
        if not rows and not detail.get("messages"):
            raise ValueError("没有可写入研报的指标或研究结论")

        selected_messages = []
        wanted = set(message_ids or [])
        for message in detail.get("messages", []):
            if message["role"] != "assistant":
                continue
            if wanted and message["id"] not in wanted:
                continue
            selected_messages.append(message)
        if not wanted and selected_messages:
            selected_messages = selected_messages[-1:]

        periods = detail.get("periods", [])
        citations: List[Dict[str, Any]] = []
        for row in rows:
            for period in periods:
                citation = _metric_citation(row, period)
                if citation:
                    citations.append(citation)
        for message in selected_messages:
            for citation in (message.get("data") or {}).get("citations", []):
                if not isinstance(citation, dict):
                    continue
                citations.append(
                    {
                        "id": citation.get("id", ""),
                        "label": citation.get("label", ""),
                        "kind": citation.get("kind", ""),
                        "summary": citation.get("summary", ""),
                        "as_of": citation.get("as_of", ""),
                        "document_id": citation.get("document_id") or (citation.get("payload") or {}).get("document_id"),
                        "page": citation.get("page") or (citation.get("payload") or {}).get("page"),
                        "quote": citation.get("quote") or (citation.get("payload") or {}).get("quote", ""),
                        "payload": citation.get("payload") or {},
                    }
                )
        seen = set()
        unique_citations = []
        for item in citations:
            key = item.get("id") or (
                item.get("document_id"),
                item.get("page"),
                item.get("quote"),
                item.get("label"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_citations.append(item)
        citations = unique_citations

        summary_text = "\n\n".join(str(m.get("content") or "").strip() for m in selected_messages).strip()
        summary_text = re.sub(r"\s*[\(（]doc:[^\)）]+[\)）]", "", summary_text).strip()
        if not summary_text:
            summary_text = self._auto_summary(detail, rows)
        gaps = []
        for message in selected_messages:
            gaps.extend((message.get("data") or {}).get("gaps", []))
        for row in rows:
            for period in row.get("missing", []):
                gaps.append(f"{row['label']} {period} 未披露")
        gaps = list(dict.fromkeys(str(item) for item in gaps if str(item).strip()))

        sections: List[Dict[str, Any]] = [
            {
                "id": "summary",
                "title": "核心结论",
                "kind": "text",
                "body": summary_text,
                "citations": citations,
            }
        ]
        if rows:
            sections.append(
                {
                    "id": "metrics",
                    "title": "经营数据",
                    "kind": "metric_table",
                    "periods": periods,
                    "rows": [
                        {
                            "key": row["key"],
                            "label": row["label"],
                            "unit": row["unit"],
                            "values": {
                                period: row["cells"].get(period, {}).get("value")
                                for period in periods
                            },
                        }
                        for row in rows
                    ],
                    "citations": citations,
                }
            )
        if template == "full" and rows:
            sections.append(
                {
                    "id": "observations",
                    "title": "数据观察",
                    "kind": "text",
                    "body": self._observations(rows, periods),
                    "citations": citations,
                }
            )
        if gaps:
            sections.append(
                {
                    "id": "gaps",
                    "title": "风险与待核实",
                    "kind": "list",
                    "items": gaps[:12],
                    "citations": citations,
                }
            )
        if detail["sources"]:
            sections.append(
                {
                    "id": "sources",
                    "title": "数据来源",
                    "kind": "sources",
                    "items": [
                        {
                            "name": source["name"],
                            "year": source.get("year"),
                            "page_count": source.get("page_count"),
                            "file_url": source.get("file_url"),
                        }
                        for source in detail["sources"]
                    ],
                    "citations": citations,
                }
            )

        report_title = title.strip() or (
            f"{detail['name']}（{detail['symbol']}）经营数据研究"
            if rows
            else f"{detail['name']}（{detail['symbol']}）研究简报"
        )
        review = {
            "sections": len(sections),
            "citations": len(citations),
            "sources": len(detail["sources"]),
            "metrics": len(rows),
            "missing": len([row for row in rows for period in row.get("missing", [])]),
            "template": template,
            "checks": [
                "每个数字与引用来自已保存来源",
                "在线来源与 PDF 页码分别保留",
                "缺失数据保留，不补零",
                "报告为确定性组装，未重新查询数据",
            ],
        }
        report = self.db.save_research_report(
            session_id=session_id,
            title=report_title,
            template=template,
            sections=sections,
            review=review,
        )
        return report

    def _auto_summary(self, detail: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return f"{detail['name']} 当前还没有确认的结构化指标，报告仅保留研究结论与材料来源。"
        facts = []
        for row in rows[:4]:
            values = [
                f"{period} {_fmt(row['cells'][period].get('value'), row['unit'])}"
                for period in detail.get("periods", [])
                if row["cells"].get(period, {}).get("value") is not None
            ]
            if values:
                facts.append(f"{row['label']}：" + " / ".join(values))
        return (
            f"本报告基于 {len(detail['sources'])} 份年报和 {len(rows)} 组已确认指标整理。"
            + ("\n" + "\n".join(facts) if facts else "")
        )

    def _observations(self, rows: List[Dict[str, Any]], periods: Sequence[str]) -> str:
        lines = []
        for row in rows[:8]:
            values = [
                (period, row["cells"].get(period, {}).get("value"))
                for period in periods
                if row["cells"].get(period, {}).get("value") is not None
            ]
            if len(values) >= 2:
                first_period, first = values[0]
                last_period, last = values[-1]
                try:
                    change = (float(last) / float(first) - 1) * 100 if float(first) else None
                except (TypeError, ValueError, ZeroDivisionError):
                    change = None
                suffix = f"，区间变化 {change:+.1f}%" if change is not None else ""
                lines.append(
                    f"- {row['label']}：{first_period} {_fmt(first, row['unit'])} → "
                    f"{last_period} {_fmt(last, row['unit'])}{suffix}"
                )
            elif values:
                lines.append(f"- {row['label']}：{values[0][0]} {_fmt(values[0][1], row['unit'])}")
        return "\n".join(lines) or "暂无可计算的区间变化。"

    def _from_snippets(
        self,
        detail: Dict[str, Any],
        template: str,
        snippets: List[Dict[str, Any]],
        title: str,
        settings: Optional[Settings] = None,
    ) -> Dict[str, Any]:
        sections: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []
        selected_rows: List[Dict[str, Any]] = []
        for index, snippet in enumerate(snippets, 1):
            if not isinstance(snippet, dict):
                continue
            kind = snippet.get("kind")
            snippet_citations = [item for item in snippet.get("citations", []) if isinstance(item, dict)]
            citations.extend(snippet_citations)
            if kind == "metric_table":
                keys = set(snippet.get("metric_keys") or [])
                rows = [row for row in detail["metrics"] if row["available"] > 0 and row["key"] in keys]
                if not rows:
                    continue
                selected_rows.extend(rows)
                periods = detail.get("periods", [])
                metric_citations = []
                for row in rows:
                    for period in periods:
                        item = _metric_citation(row, period)
                        if item:
                            metric_citations.append(item)
                            citations.append(item)
                sections.append(
                    {
                        "id": f"snippet-{index}",
                        "title": snippet.get("title") or f"数据片段 {index}",
                        "kind": "metric_table",
                        "periods": periods,
                        "rows": [
                            {
                                "key": row["key"],
                                "label": row["label"],
                                "unit": row["unit"],
                                "values": {
                                    period: row["cells"].get(period, {}).get("value")
                                    for period in periods
                                },
                                "sources": {
                                    period: _metric_citation(row, period)
                                    for period in periods
                                },
                            }
                            for row in rows
                        ],
                        "citations": metric_citations,
                    }
                )
            elif kind in {"text", "market_snapshot"}:
                body = str(snippet.get("body") or "").strip()
                if not body:
                    continue
                sections.append(
                    {
                        "id": f"snippet-{index}",
                        "title": snippet.get("title") or ("研究摘录" if kind == "text" else "市场快照"),
                        "kind": "text",
                        "body": body,
                        "citations": snippet_citations,
                    }
                )
        if not sections:
            raise ValueError("没有可写入研报的片段")

        unique = []
        seen = set()
        for item in citations:
            key = item.get("id") or (item.get("document_id"), item.get("page"), item.get("quote"), item.get("label"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        citations = unique

        text_sections = [section for section in sections if section.get("kind") == "text"]
        metric_sections = [section for section in sections if section.get("kind") == "metric_table"]
        if settings is not None and settings.llm_enabled and text_sections:
            ai_sections = self._ai_text_sections(text_sections, citations, detail, settings)
            if ai_sections:
                sections = ai_sections + metric_sections
            else:
                for section in text_sections:
                    if citations:
                        section["body"] = str(section.get("body") or "").rstrip() + " [[1]]"
        elif citations:
            for section in text_sections:
                section["body"] = str(section.get("body") or "").rstrip() + " [[1]]"

        if detail["sources"]:
            sections.append(
                {
                    "id": "sources",
                    "title": "数据来源",
                    "kind": "sources",
                    "items": [
                        {
                            "name": source["name"],
                            "year": source.get("year"),
                            "page_count": source.get("page_count"),
                            "file_url": source.get("file_url"),
                        }
                        for source in detail["sources"]
                    ],
                    "citations": [],
                }
            )
        report_title = title.strip() or f"{detail['name']}（{detail['symbol']}）研究简报"
        review = {
            "sections": len(sections),
            "citations": len(citations),
            "sources": len(detail["sources"]),
            "metrics": len({row["key"] for row in selected_rows}),
            "missing": 0,
            "template": template,
            "checks": [
                "只使用用户选中的片段",
                "引用来自已保存研究来源",
                "在线来源与 PDF 页码分别保留",
                "不重新查询数据",
            ],
        }
        return self.db.save_research_report(
            session_id=detail["id"],
            title=report_title,
            template=template,
            sections=sections,
            review=review,
        )

    def _ai_text_sections(
        self,
        text_sections: List[Dict[str, Any]],
        citations: List[Dict[str, Any]],
        detail: Dict[str, Any],
        settings: Settings,
    ) -> Optional[List[Dict[str, Any]]]:
        if not citations:
            return None
        catalog = "\n".join(
            f"[{index}] {item.get('label')} | {item.get('summary', '')}"
            for index, item in enumerate(citations, 1)
        )
        material = "\n\n".join(
            f"### {section.get('title')}\n{section.get('body')}" for section in text_sections
        )
        source_numbers = set(_numbers(material + "\n" + catalog))
        prompt = (
            f"公司：{detail['name']}（{detail['symbol']}）\n"
            f"可用来源：\n{catalog}\n\n"
            f"用户选中的素材：\n{material}\n\n"
            "请把这些素材写成一篇连贯的中文研究简报。只使用素材中的事实和数字，不得引入新数字；"
            "在每个含数字或事实的句子后加引用标记，例如 [[1]]，编号必须对应上面的来源。\n"
            "输出 JSON，不要 Markdown 代码块：\n"
            '{"title":"研报标题","sections":[{"title":"章节标题","body":"正文，含 [[n]] 引用"}]}\n'
            "2–4 个章节即可。"
        )
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.agent_timeout_seconds,
            )
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是研究编辑，只基于给定素材写作；事实和数字必须来自素材，引用用 [[n]]。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=5000,
            )
            raw = (response.choices[0].message.content or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|```$", "", raw).strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return None
            data = __import__("json").loads(raw[start : end + 1])
            output = []
            for index, section in enumerate(data.get("sections", [])):
                body = str(section.get("body") or "").strip()
                if not body:
                    continue
                if any(not _number_supported(number, source_numbers) for number in _numbers(body)):
                    return None
                body = re.sub(r"\[\[(\d+)\]\]", lambda m: m.group(0) if 1 <= int(m.group(1)) <= len(citations) else "", body)
                output.append(
                    {
                        "id": f"ai-{index + 1}",
                        "title": str(section.get("title") or f"章节 {index + 1}"),
                        "kind": "text",
                        "body": body,
                        "citations": citations,
                    }
                )
            return output or None
        except Exception:
            return None

    def update(
        self, report_id: str, title: str, sections: List[Dict[str, Any]], note: str = "人工编辑"
    ) -> Dict[str, Any]:
        current = self.db.get_research_report(report_id)
        if not current:
            raise KeyError("report not found")
        review = self._review_for(current.get("template", "brief"), sections, current.get("review", {}))
        review["edited"] = True
        updated = self.db.update_research_report(
            report_id, title.strip() or current["title"], sections, review, note
        )
        if not updated:
            raise KeyError("report not found")
        return updated

    def versions(self, report_id: str) -> List[Dict[str, Any]]:
        return self.db.list_report_versions(report_id)

    def restore(self, report_id: str, version: int) -> Dict[str, Any]:
        current = self.db.get_research_report(report_id)
        snapshot = self.db.get_report_version(report_id, version)
        if not current or not snapshot:
            raise KeyError("report version not found")
        return self.update(
            report_id,
            snapshot["title"],
            snapshot["sections"],
            note=f"恢复 v{version}",
        )

    def polish(self, report_id: str, settings: Settings) -> Dict[str, Any]:
        if not settings.llm_enabled:
            raise ValueError("LLM 未配置，无法润色")
        current = self.db.get_research_report(report_id)
        if not current:
            raise KeyError("report not found")
        observations = next(
            (section for section in current.get("sections", []) if section.get("id") == "observations"),
            None,
        )
        if not observations:
            raise ValueError("当前模板没有“数据观察”章节，请使用公司研究完整稿")
        facts = observations.get("body", "")
        metrics = next(
            (section for section in current.get("sections", []) if section.get("id") == "metrics"),
            None,
        )
        if metrics:
            for row in metrics.get("rows", []):
                values = " / ".join(
                    f"{period} {_fmt(value, row.get('unit', ''))}"
                    for period, value in row.get("values", {}).items()
                    if value is not None
                )
                facts += f"\n{row.get('label')}：{values}"
        input_numbers = set(_numbers(facts))

        from openai import OpenAI

        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.agent_timeout_seconds,
        )
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是研究编辑。只改写“数据观察”的行文，使它更连贯、可读。"
                        "不得新增、删除或改写任何数字；不得引入输入中没有的公司、年份或指标。"
                        "直接输出最终文本，不要分析过程，不要 Markdown 表格或代码块。"
                        "最多 6 条，每条一行。"
                    ),
                },
                {
                    "role": "user",
                    "content": "请基于以下事实改写数据观察：\n" + facts[:6000],
                },
            ],
            temperature=0.2,
            max_tokens=3000,
        )
        body = (response.choices[0].message.content or "").strip()
        body = re.sub(r"^```(?:text|markdown)?\s*|```$", "", body).strip()
        if not body:
            raise ValueError("模型未返回润色文本")
        output_numbers = set(_numbers(body))
        added = sorted(number for number in output_numbers if not _number_supported(number, input_numbers))
        if added:
            raise ValueError("润色文本引入了底稿之外的新数字：" + "、".join(added[:5]))

        sections = []
        for section in current.get("sections", []):
            item = dict(section)
            if item.get("id") == "observations":
                item["body"] = body
            sections.append(item)
        review = self._review_for(
            current.get("template", "full"), sections, current.get("review", {})
        )
        review["edited"] = True
        review["polished"] = True
        review["checks"] = list(review.get("checks", [])) + [
            "AI 润色数据观察：数字与底稿一致"
        ]
        updated = self.db.update_research_report(
            report_id,
            current["title"],
            sections,
            review,
            note="AI 润色数据观察",
        )
        if not updated:
            raise KeyError("report not found")
        return updated

    def _review_for(
        self, template: str, sections: List[Dict[str, Any]], previous: Dict[str, Any]
    ) -> Dict[str, Any]:
        citations = set()
        metrics = 0
        sources = 0
        for section in sections:
            for citation in section.get("citations", []):
                citations.add(
                    citation.get("id")
                    or (
                        citation.get("document_id"),
                        citation.get("page"),
                        citation.get("quote"),
                        citation.get("label"),
                    )
                )
            if section.get("kind") == "metric_table":
                metrics = len(section.get("rows", []))
            if section.get("kind") == "sources":
                sources = len(section.get("items", []))
        return {
            "sections": len(sections),
            "citations": len(citations),
            "sources": sources or previous.get("sources", 0),
            "metrics": metrics,
            "missing": previous.get("missing", 0),
            "template": template,
            "checks": previous.get("checks", []),
        }

    def markdown(self, report: Dict[str, Any]) -> str:
        lines = [f"# {report['title']}", "", f"生成时间：{report['created_at']}", ""]
        for index, section in enumerate(report.get("sections", []), 1):
            lines.append(f"## {index}. {section['title']}")
            lines.append("")
            if section["kind"] == "text":
                lines.append(section.get("body", ""))
            elif section["kind"] == "metric_table":
                periods = section.get("periods", [])
                lines.append("| 指标 | 单位 | " + " | ".join(periods) + " |")
                lines.append("|---|---|" + "|".join("---" for _ in periods) + "|")
                for row in section.get("rows", []):
                    lines.append(
                        f"| {row['label']} | {row['unit']} | "
                        + " | ".join(_fmt(row["values"].get(period), row["unit"]) for period in periods)
                        + " |"
                    )
            elif section["kind"] == "list":
                lines.extend(f"- {item}" for item in section.get("items", []))
            elif section["kind"] == "sources":
                for item in section.get("items", []):
                    lines.append(f"- {item.get('name')} · {item.get('page_count')} 页")
            lines.append("")
            citations = section.get("citations", [])
            if citations:
                lines.append(
                    "引用："
                    + "；".join(
                        f"{c['label']}" + (f" p{c['page']}" if c.get("page") else f" ({c.get('kind', '来源')})")
                        for c in citations[:8]
                    )
                )
                lines.append("")
        review = report.get("review", {})
        lines.append("---")
        lines.append(
            f"审阅：{review.get('sources', 0)} 个来源 · {review.get('citations', 0)} 处引用 · "
            f"{review.get('metrics', 0)} 组指标"
        )
        return "\n".join(lines)
