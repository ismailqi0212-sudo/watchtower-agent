"""Deterministic metric extraction for the 网易云音乐 annual-report demo.

This is intentionally a domain adapter, not an agent.  It turns parsed PDF
pages into *verified* metric cells with a physical page and a quote.  The
research Agent can read these cells through tools, but it never parses PDFs
itself.

The extractor is conservative: a value is emitted only when a pattern matches
the page text.  Missing years remain missing instead of being inferred.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TRADITIONAL = {
    "在線音樂服務": "在线音乐服务",
    "社交娛樂服務": "社交娱乐服务",
    "月付費用戶數": "月付费用户数",
    "每月每付費用戶收入": "每月每付费用户收入",
    "月活躍用戶數": "月活跃用户数",
    "百萬人": "百万人",
    "人民幣": "人民币",
    "百萬元": "百万元",
    "經營活動": "经营活动",
    "現金淨額": "现金净额",
    "歸屬於": "归属于",
    "年內": "年内",
    "利潤": "利润",
    "虧損": "亏损",
    "權益持有人": "权益持有人",
    "所得╱（所用）": "所得/（所用）",
}


def normalize_text(text: str) -> str:
    for old, new in TRADITIONAL.items():
        text = text.replace(old, new)
    return text.replace("\u00a0", " ").replace("╱", "/")


def _num(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "").replace("，", ""))
    except ValueError:
        return None


def _million_from(raw: str) -> float:
    """Normalize a statement amount to CNY million.

    Annual-report statements are usually in CNY thousand.  Narrative MD&A
    amounts are already in CNY million.  We only convert when the magnitude
    makes the unit unambiguous.
    """
    value = _num(raw)
    if value is None:
        raise ValueError(raw)
    if abs(value) >= 100000:
        return round(value / 1000.0, 3)
    return round(value, 3)


def _snippet(text: str, start: int, end: int, width: int = 140) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _page_text(pages: Sequence[Dict[str, Any]], page: int) -> str:
    for item in pages:
        if item.get("page") == page:
            return normalize_text(item.get("text") or "")
    return ""


def _find_page(
    pages: Sequence[Dict[str, Any]], *needles: str, exclude: Sequence[str] = ()
) -> Optional[Tuple[int, str]]:
    for item in pages:
        text = normalize_text(item.get("text") or "")
        if all(needle in text for needle in needles) and not any(
            bad in text for bad in exclude
        ):
            return int(item["page"]), text
    return None


def _match(pattern: str, text: str) -> Optional[re.Match[str]]:
    return re.search(pattern, text, flags=re.S)


def _business_metrics(
    year: int, pages: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    found = _find_page(pages, "月付费用户数", exclude=("释义",))
    if not found:
        return []
    page, text = found

    pay = _match(
        r"月付费用户数（千人）\s*"
        r"在线音乐服务\s*([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s*"
        r"社交娱乐服务\s*([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)",
        text,
    )
    arpu = _match(
        r"每月每付费用户收入（人民币元）\s*"
        r"在线音乐服务(?:\(\d\))?\s*([\d.]+)\s+([\d.]+)\s*"
        r"社交娱乐服务(?:\(\d\))?\s*([\d.]+)\s+([\d.]+)",
        text,
    )
    mau = _match(
        r"在线音乐服务月活跃用户数（百万人）\s*([\d.]+)\s+([\d.]+)", text
    )

    result: List[Dict[str, Any]] = []

    def add(
        key: str,
        label: str,
        unit: str,
        value: Optional[str],
        match: Optional[re.Match[str]],
    ) -> None:
        number = _num(value)
        if number is None or match is None:
            return
        result.append(
            {
                "metric_key": key,
                "label": label,
                "unit": unit,
                "period": str(year),
                "value": round(number, 3),
                "page": page,
                "quote": _snippet(text, match.start(), match.end()),
                "status": "verified",
            }
        )

    if pay:
        add("online_paying_users", "在线音乐月付费用户", "千人", pay.group(1), pay)
        add("social_paying_users", "社交娱乐月付费用户", "千人", pay.group(3), pay)
    if arpu:
        add("online_arpu", "在线音乐 ARPU", "元/月", arpu.group(1), arpu)
        add("social_arpu", "社交娱乐 ARPU", "元/月", arpu.group(3), arpu)
    if mau:
        add("online_mau", "在线音乐月活跃用户", "百万人", mau.group(1), mau)
    return result


def _financial_value(
    pages: Sequence[Dict[str, Any]],
    label_candidates: Iterable[str],
    year: int,
) -> Optional[Tuple[float, int, str]]:
    """Find the current-year statement value next to a row label."""
    for item in pages:
        page = int(item["page"])
        text = normalize_text(item.get("text") or "")
        for label in label_candidates:
            # Narrative form: "收入由2021年的人民币...至2022年的人民币8,992.2百万元"
            m = _match(
                rf"{re.escape(label)}由\d{{4}}年的人民币[\d,.]+百万元"
                rf"[^。]{{0,40}}?至{year}年的人民币([\d,.]+)百万元",
                text,
            )
            if m:
                return _million_from(m.group(1)), page, _snippet(text, m.start(), m.end())
            # Narrative form: "收入人民币6,997.6百万元"
            m = _match(
                rf"{re.escape(label)}(?:为|录得|约)?人民币([\d,.]+)百万元", text
            )
            if m:
                return _million_from(m.group(1)), page, _snippet(text, m.start(), m.end())
            # Statement form: label on one line, current value on the next.
            m = _match(
                rf"{re.escape(label)}\s*[\(（]?([\d,]+(?:\.\d+)?)[\)）]?", text
            )
            if m:
                return _million_from(m.group(1)), page, _snippet(text, m.start(), m.end())
    return None


def _net_profit(
    year: int, pages: Sequence[Dict[str, Any]]
) -> Optional[Tuple[float, int, str]]:
    labels = [
        "归属于本公司权益持有人的年内利润",
        "归属于本公司权益持有人的年内亏损",
        "本公司权益持有人应占年内利润",
        "本公司权益持有人应占年内亏损",
        "年内利润",
        "年内亏损",
        "归属于本公司权益持有人的年内利润/（亏损）",
        "本公司权益持有人应占年内利润/（亏损）",
        "年内利润/（亏损）",
    ]
    for item in pages:
        page = int(item["page"])
        text = normalize_text(item.get("text") or "")
        for label in labels:
            m = _match(
                rf"{re.escape(label)}\s*([\(（]?)([\d,]+(?:\.\d+)?)([\)）]?)",
                text,
            )
            if not m:
                continue
            raw = m.group(2)
            negative = bool(m.group(1) or m.group(3))
            value = _million_from(raw)
            if negative:
                value = -abs(value)
            return value, page, _snippet(text, m.start(), m.end())
    return None


def _repair_split_numbers(text: str) -> str:
    """Join wrapped table cells such as ``1,774,6`` + ``20``.

    Only a short continuation line is joined, and only when the previous line
    already looks like a number. This avoids merging two adjacent columns.
    """
    lines = text.splitlines()
    out: List[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        while (
            index + 1 < len(lines)
            and re.fullmatch(r"\d{1,3}", lines[index + 1].strip())
            and re.search(r"\d$", line.strip())
            and ("," in line or "." in line or len(line.strip()) >= 5)
        ):
            line = line.rstrip() + lines[index + 1].strip()
            index += 1
        out.append(line)
        index += 1
    return "\n".join(out)


def _cash_flow(
    year: int, pages: Sequence[Dict[str, Any]]
) -> Optional[Tuple[float, int, str]]:
    for item in pages:
        page = int(item["page"])
        text = _repair_split_numbers(normalize_text(item.get("text") or ""))
        for label in ("经营活动所得现金净额", "经营活动所得/（所用）现金净额", "经营活动所得╱（所用）现金净额", "经营活动所用现金净额"):
            m = _match(
                rf"{re.escape(label)}\s*([\(（]?)([\d,]+(?:\.\d+)?)([\)）]?)",
                text,
            )
            if not m:
                continue
            negative = bool(m.group(1) or m.group(3))
            value = _million_from(m.group(2))
            if negative:
                value = -abs(value)
            return value, page, _snippet(text, m.start(), m.end())
    return None


def _gross_margin(
    year: int, pages: Sequence[Dict[str, Any]]
) -> Optional[Tuple[float, int, str]]:
    for item in pages:
        page = int(item["page"])
        text = normalize_text(item.get("text") or "")
        patterns = [
            rf"毛利率由[^。]{{0,40}}?至{year}年的([\d.]+)%",
            rf"毛利率(?:为|达|录得)?\s*([\d.]+)%",
        ]
        for pattern in patterns:
            m = _match(pattern, text)
            if m:
                return round(float(m.group(1)), 3), page, _snippet(text, m.start(), m.end())
    return None


def extract_yanji_cloud_metrics(
    year: int, pages: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Extract the sample company's business + financial metrics."""
    result: List[Dict[str, Any]] = []

    def add_value(
        key: str,
        label: str,
        unit: str,
        found: Optional[Tuple[float, int, str]],
    ) -> None:
        if not found:
            return
        value, page, quote = found
        result.append(
            {
                "metric_key": key,
                "label": label,
                "unit": unit,
                "period": str(year),
                "value": round(value, 3),
                "page": page,
                "quote": quote,
                "status": "verified",
            }
        )

    result.extend(_business_metrics(year, pages))

    add_value("revenue", "收入", "百万元", _financial_value(pages, ["收入"], year))
    add_value("gross_profit", "毛利", "百万元", _financial_value(pages, ["毛利"], year))
    add_value("gross_margin", "毛利率", "%", _gross_margin(year, pages))
    add_value("net_profit", "净利润", "百万元", _net_profit(year, pages))
    add_value("operating_cash_flow", "经营现金流", "百万元", _cash_flow(year, pages))

    return result
