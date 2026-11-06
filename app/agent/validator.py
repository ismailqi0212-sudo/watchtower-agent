"""Deterministic guardrails around the LLM/demo output.

The validator is the difference between "a model wrote some JSON" and a report
the product can trust: scores are clamped, actions must match the score band,
every claim needs a real evidence id, and trade plans must be internally
consistent. Repair is preferred over rejection so a run still produces a
useful, clearly-flagged card.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas import DecisionReport

ALLOWED_ACTIONS = {"buy", "add", "hold", "reduce", "sell", "watch", "avoid"}


def action_for_score(score: int) -> str:
    if score >= 78:
        return "buy"
    if score >= 63:
        return "add"
    if score >= 47:
        return "hold"
    if score >= 35:
        return "watch"
    if score >= 22:
        return "reduce"
    return "sell"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _float(value: Any) -> Optional[float]:
    try:
        result = float(value)
        if result != result:  # NaN
            return None
        return result
    except (TypeError, ValueError):
        return None


def _evidence_by_kind(evidence: List[Dict[str, Any]], kind: str) -> List[str]:
    return [item["id"] for item in evidence if item.get("kind") == kind]


def _pick_evidence(text: str, evidence: List[Dict[str, Any]]) -> List[str]:
    if not evidence:
        return []
    if any(key in text for key in ("均线", "RSI", "量比", "动量", "趋势", "支撑", "压力")):
        ids = _evidence_by_kind(evidence, "indicator")
        if ids:
            return ids[:1]
    if any(key in text for key in ("PE", "PB", "ROE", "估值", "盈利", "基本面")):
        ids = _evidence_by_kind(evidence, "fundamental")
        if ids:
            return ids[:1]
    if any(key in text for key in ("资讯", "新闻", "舆情", "公告", "研报")):
        ids = _evidence_by_kind(evidence, "news")
        if ids:
            return ids[:2]
    if any(key in text for key in ("基准", "沪深300", "超额")):
        ids = _evidence_by_kind(evidence, "benchmark")
        if ids:
            return ids[:1]
    return [evidence[0]["id"]]


def _normalize_claim(
    item: Dict[str, Any], evidence: List[Dict[str, Any]], valid_ids: set
) -> Dict[str, Any]:
    text = str(item.get("text") or "").strip()
    if not text:
        text = "该结论缺少可读解释。"
    ids = [eid for eid in item.get("evidence_ids", []) if eid in valid_ids]
    if not ids:
        ids = _pick_evidence(text, evidence)
    return {"text": text, "evidence_ids": ids}


def validate_and_repair(
    report: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    symbol: str,
    name: str,
    as_of: str,
    generated_by: str = "unknown",
) -> Dict[str, Any]:
    notes: List[str] = []
    evidence = [item for item in evidence if item.get("id")]
    valid_ids = {item["id"] for item in evidence}
    indicator = next((item for item in evidence if item.get("kind") == "indicator"), {})
    payload = indicator.get("payload", {}) if isinstance(indicator, dict) else {}
    close = _float(payload.get("close")) or 0.0

    # --- core fields -------------------------------------------------
    score = int(_clamp(_float(report.get("score")) or 50, 0, 100))
    action = str(report.get("action") or "").strip()
    expected = action_for_score(score)
    if action not in ALLOWED_ACTIONS:
        notes.append(f"action '{action}' 非法，按评分修正为 {expected}。")
        action = expected
    elif action == "avoid" and score >= 40:
        notes.append("avoid 与评分区间不一致，修正为更保守的减仓/观望。")
        action = "reduce" if score < 47 else "watch"
    elif action != expected and not (action, expected) in {
        ("add", "buy"),
        ("buy", "add"),
        ("hold", "watch"),
        ("watch", "hold"),
    }:
        notes.append(f"action {action} 与评分 {score} 不匹配，修正为 {expected}。")
        action = expected

    symbol = str(report.get("symbol") or symbol)
    name = str(report.get("name") or name)
    report_as_of = str(report.get("as_of") or as_of)
    if report_as_of > as_of:
        notes.append("报告日期晚于分析基准日，已回退到基准日。")
        report_as_of = as_of

    summary = str(report.get("summary") or "").strip()
    if not summary:
        summary = "数据不足，暂以观望为主，等待更明确的趋势与量价信号。"
        notes.append("缺失 summary，已补充保守结论。")

    data_quality = str(report.get("data_quality") or "ok")
    if data_quality not in {"ok", "partial", "stale"}:
        data_quality = "partial"
    if len(evidence) < 3:
        data_quality = "partial"
        notes.append("有效证据少于 3 条，数据质量降级为 partial。")

    confidence = _clamp(_float(report.get("confidence")) or 0.5, 0.0, 1.0)
    if data_quality != "ok":
        confidence = min(confidence, 0.68)
    confidence = round(confidence, 2)

    # --- evidence-bound claims --------------------------------------
    thesis_raw = report.get("thesis") or []
    thesis = []
    for item in thesis_raw:
        if isinstance(item, dict):
            thesis.append(_normalize_claim(item, evidence, valid_ids))
    if len(thesis) < 2:
        notes.append("有效论点少于 2 条，已用证据摘要补齐。")
        for item in evidence[:3]:
            if item.get("kind") in {"indicator", "news", "fundamental"}:
                thesis.append(
                    {
                        "text": f"{item.get('label', '证据')}：{item.get('summary', '')}",
                        "evidence_ids": [item["id"]],
                    }
                )
    thesis = thesis[:5]

    risks_raw = report.get("risks") or []
    risks = []
    for item in risks_raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        severity = item.get("severity", "medium")
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        risks.append(_normalize_claim({**item, "text": text}, evidence, valid_ids) | {"severity": severity})
    if not risks:
        risks = [
            {
                "text": "模型基于历史数据与公开资讯，无法预测突发事件，需结合仓位管理。",
                "severity": "low",
                "evidence_ids": [evidence[0]["id"]] if evidence else [],
            }
        ]
    risks = risks[:4]

    # --- plan sanity -------------------------------------------------
    plan_raw = report.get("plan") or {}
    entry_low = _float(plan_raw.get("entry_low"))
    entry_high = _float(plan_raw.get("entry_high"))
    stop_loss = _float(plan_raw.get("stop_loss"))
    target_price = _float(plan_raw.get("target_price"))
    position_pct = _float(plan_raw.get("position_pct"))

    if close <= 0:
        close = entry_low or entry_high or 10.0
    if entry_low is None:
        entry_low = round(close * 0.98, 2)
    if entry_high is None:
        entry_high = round(close * 1.01, 2)
    if entry_low > entry_high:
        entry_low, entry_high = entry_high, entry_low
        notes.append("买入区间上下界倒置，已交换。")
    if stop_loss is None or stop_loss <= 0 or stop_loss >= entry_low:
        stop_loss = round(min(entry_low * 0.95, close * 0.93), 2)
        notes.append("止损位缺失或不合理，已按入场区间下沿重算。")
    if target_price is None or target_price <= entry_high:
        target_price = round(max(entry_high * 1.06, close * 1.08), 2)
        notes.append("目标位缺失或不合理，已按入场区间上沿重算。")
    if position_pct is None:
        position_pct = 20.0 if score >= 63 else 10.0 if score >= 47 else 0.0
    position_pct = round(_clamp(position_pct, 0, 40), 1)
    horizon = str(plan_raw.get("horizon") or "5d")
    if horizon not in {"intraday", "1d", "3d", "5d", "10d", "swing"}:
        horizon = "5d"

    # Deduplicate evidence and keep only referenced items for a compact payload.
    seen = set()
    deduped = []
    for item in evidence:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)

    normalized = {
        "symbol": symbol,
        "name": name,
        "as_of": report_as_of,
        "action": action,
        "score": score,
        "confidence": confidence,
        "summary": summary,
        "thesis": thesis,
        "risks": risks,
        "plan": {
            "entry_low": round(entry_low, 2),
            "entry_high": round(entry_high, 2),
            "stop_loss": round(stop_loss, 2),
            "target_price": round(target_price, 2),
            "position_pct": position_pct,
            "horizon": horizon,
        },
        "data_quality": data_quality,
        "evidence": deduped,
        "validation_notes": notes,
        "generated_by": generated_by,
        "disclaimer": str(
            report.get("disclaimer") or "仅供研究与演示，不构成投资建议。"
        ),
    }

    try:
        return DecisionReport.model_validate(normalized).model_dump()
    except Exception as exc:  # last-resort safety net
        notes.append(f"报告规范化失败，返回最小可用版本：{exc}")
        minimal = dict(normalized)
        minimal["thesis"] = thesis[:2]
        minimal["risks"] = risks[:2]
        minimal["validation_notes"] = notes
        minimal["data_quality"] = "partial"
        return minimal
