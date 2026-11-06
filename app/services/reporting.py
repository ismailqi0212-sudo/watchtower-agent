"""Markdown rendering for exported reports."""

from __future__ import annotations

from typing import Any, Dict

from app.schemas import ACTION_LABELS


def render_markdown(report: Dict[str, Any]) -> str:
    action = report.get("action", "watch")
    label = ACTION_LABELS.get(action, action)
    plan = report.get("plan", {})
    evidence = {item["id"]: item for item in report.get("evidence", [])}
    lines = [
        f"# {report.get('name', '')}（{report.get('symbol', '')}）复盘",
        "",
        f"> {report.get('as_of', '')} · **{label}** · 评分 {report.get('score', 0)}/100 "
        f"· 置信度 {report.get('confidence', 0):.0%} · 数据质量 {report.get('data_quality', 'ok')}",
        "",
        report.get("summary", ""),
        "",
        "## 交易计划",
        "",
        "| 项目 | 数值 |",
        "|---|---|",
        f"| 入场区间 | {plan.get('entry_low', 'N/A')} – {plan.get('entry_high', 'N/A')} |",
        f"| 止损 | {plan.get('stop_loss', 'N/A')} |",
        f"| 目标 | {plan.get('target_price', 'N/A')} |",
        f"| 建议仓位 | {plan.get('position_pct', 'N/A')}% |",
        f"| 持有周期 | {plan.get('horizon', 'N/A')} |",
        "",
        "## 核心论点",
        "",
    ]
    for item in report.get("thesis", []):
        refs = " ".join(
            f"[{eid}](evidence://{eid})" for eid in item.get("evidence_ids", [])[:4]
        )
        lines.append(f"- {item.get('text', '')}  \n  `{refs}`")
    lines.extend(["", "## 风险", ""])
    for item in report.get("risks", []):
        lines.append(
            f"- **[{item.get('severity', 'medium')}]** {item.get('text', '')}"
        )
    lines.extend(["", "## 证据", ""])
    for eid, item in evidence.items():
        lines.append(f"- `{eid}` · {item.get('label', '')}：{item.get('summary', '')}")
    if report.get("validation_notes"):
        lines.extend(["", "## 校验说明", ""])
        for note in report["validation_notes"]:
            lines.append(f"- {note}")
    lines.extend(["", "---", "", report.get("disclaimer", "")])
    return "\n".join(lines)
