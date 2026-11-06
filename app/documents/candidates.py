"""Generic metric-candidate scanner for uploaded annual reports.

This is a review-first extractor: it proposes labels/values with page evidence,
but does not write them into the worksheet until the user confirms them.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


YEAR = re.compile(r"(20\d{2})")
NUMBER = re.compile(r"^[\(（]?[-+−]?[\d,]+(?:\.\d+)?[\)）]?%?$")
SKIP_LABELS = {
    "",
    "项目",
    "附注",
    "截至",
    "年度",
    "人民币",
    "变动",
}


def _compact(value: str) -> str:
    value = re.sub(r"(?<=\d)\s+(?=\d)", "", str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def parse_number(raw: str) -> Optional[float]:
    text = _compact(raw)
    if not text or text in {"—", "–", "-", "不适用", "n.a.", "N/A"}:
        return None
    percent = "%" in text or "％" in text
    text = text.replace(",", "").replace("，", "").replace("%", "").replace("％", "")
    negative = text.startswith("(") or text.startswith("（") or text.startswith("-")
    text = text.strip("()（）+-− ")
    try:
        value = float(text)
    except ValueError:
        return None
    if negative:
        value = -abs(value)
    return round(value, 6)


def _label(text: str) -> str:
    text = _compact(text)
    text = re.sub(r"^[（(]\d+[）)]\s*", "", text)
    text = re.sub(r"\s*[（(]?附注[）)]?.*$", "", text)
    return text.strip("：:;； ")


def _unit_for(label: str, raw: str, page_text: str) -> str:
    if "%" in raw or "％" in raw or re.search(r"(率|占比|比例)$", label):
        return "%"
    if re.search(r"千元|人民币千元", page_text):
        return "千元"
    if re.search(r"百万元|人民币百万元", page_text):
        return "百万元"
    return "元"


def _years(row: Sequence[str]) -> Dict[int, str]:
    result = {}
    for index, cell in enumerate(row):
        match = YEAR.search(cell or "")
        if match:
            result[index] = match.group(1)
    return result


def _candidate_id(document_id: str, page: int, label: str, period: str) -> str:
    digest = hashlib.sha1(f"{document_id}|{page}|{label}|{period}".encode("utf-8")).hexdigest()[:12]
    return f"cand_{digest}"


def _metric_key(label: str) -> str:
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:10]
    return f"custom_{digest}"


def scan_tables(
    document_id: str,
    document_name: str,
    tables: Sequence[Dict[str, Any]],
    page_texts: Dict[int, str],
    limit: int = 80,
) -> List[Dict[str, Any]]:
    """Return reviewable candidates from table rows with year headers."""
    candidates: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for table in tables:
        rows = table.get("rows") or []
        page = int(table.get("page") or 0)
        if not rows or not page:
            continue
        header_index = None
        years: Dict[int, str] = {}
        for index, row in enumerate(rows[:4]):
            mapping = _years(row)
            if len(mapping) >= 1:
                header_index = index
                years = mapping
                break
        if header_index is None or not years:
            continue
        page_text = page_texts.get(page, "")
        for row in rows[header_index + 1 :]:
            if not row:
                continue
            label = _label(row[0] if row else "")
            if not label or label in SKIP_LABELS or len(label) > 40:
                continue
            if YEAR.fullmatch(label):
                continue
            for column, year in years.items():
                if column >= len(row):
                    continue
                raw = row[column]
                if not NUMBER.match(_compact(raw)):
                    continue
                value = parse_number(raw)
                if value is None:
                    continue
                unit = _unit_for(label, raw, page_text)
                key = _metric_key(label)
                candidate = {
                    "candidate_id": _candidate_id(document_id, page, label, year),
                    "metric_key": key,
                    "label": label,
                    "unit": unit,
                    "period": year,
                    "value": value,
                    "document_id": document_id,
                    "document_name": document_name,
                    "page": page,
                    "quote": " | ".join(cell for cell in row if cell)[:240],
                    "status": "candidate",
                }
                dedup = (label, year)
                if dedup not in candidates:
                    candidates[dedup] = candidate
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break
    return list(candidates.values())


FINANCIAL_TERMS = re.compile(
    r"收入|毛利|利润|现金流|资产|负债|费用|研发|销售|用户|付费|ARPU|MAU|DAU|留存|毛利率|净利率|负债率",
    re.I,
)


CORE_TERMS = re.compile(r"^(收入|毛利|毛利率|净利润|经营现金流)$")


def _priority(label: str, page: int) -> int:
    if CORE_TERMS.search(label):
        return -1
    if FINANCIAL_TERMS.search(label):
        return 0
    if page <= 30:
        return 1
    return 2


def group_candidates(candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        key = item["metric_key"]
        group = grouped.setdefault(
            key,
            {
                "metric_key": key,
                "label": item["label"],
                "unit": item["unit"],
                "cells": {},
                "priority": _priority(item["label"], item["page"]),
            },
        )
        group["cells"][item["period"]] = item
    rows = list(grouped.values())
    for row in rows:
        row["periods"] = sorted(row["cells"])
    rows.sort(
        key=lambda row: (
            row["priority"],
            -len(row["periods"]),
            row["label"],
        )
    )
    return rows
