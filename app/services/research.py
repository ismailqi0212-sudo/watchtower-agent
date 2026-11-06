"""Research application service.

This is the application layer between the HTTP/Agent tools and the document
domain. It does not implement an Agent loop and it does not parse PDFs itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.research import run_research_agent
from app.agent.tools import ToolContext
from app.config import Settings
from app.db import Database
from app.documents.candidates import group_candidates, scan_tables
from app.documents.service import DocumentService
from app.documents.yanji import extract_yanji_cloud_metrics


METRIC_ORDER = [
    ("revenue", "收入", "百万元"),
    ("gross_profit", "毛利", "百万元"),
    ("gross_margin", "毛利率", "%"),
    ("net_profit", "净利润", "百万元"),
    ("operating_cash_flow", "经营现金流", "百万元"),
    ("online_mau", "在线音乐月活跃用户", "百万人"),
    ("online_paying_users", "在线音乐月付费用户", "千人"),
    ("online_arpu", "在线音乐 ARPU", "元/月"),
    ("social_paying_users", "社交娱乐月付费用户", "千人"),
    ("social_arpu", "社交娱乐 ARPU", "元/月"),
]

PERIODS = ["2021", "2022", "2023", "2024"]


class ResearchService:
    def __init__(self, db: Database, documents: DocumentService, provider: Any = None):
        self.db = db
        self.documents = documents
        self.provider = provider

    # ------------------------------------------------------------------
    # demo bootstrap: four 网易云音乐 annual reports
    # ------------------------------------------------------------------
    def bootstrap_yanji(self) -> Dict[str, Any]:
        existing = next(
            (s for s in self.db.list_research_sessions("09899") if s["status"] == "ready"),
            None,
        )
        if existing:
            detail = self.get_session(existing["id"])
            if detail and detail.get("sources"):
                if detail.get("metrics"):
                    return detail
                return self._rebuild_metrics(existing["id"], detail["sources"])

        session = self.db.create_research_session(
            symbol="09899",
            name="网易云音乐",
            question="2021–2024 年经营数据：付费用户、ARPU、毛利率与现金流",
        )
        sources = []
        for year in (2021, 2022, 2023, 2024):
            path = self.documents.uploads_dir / f"{year}.pdf"
            if not path.exists():
                continue
            document = self.documents.ingest_pdf(
                path,
                symbol="09899",
                year=year,
                name=f"{year} 年度报告",
            )
            if not document:
                continue
            self.db.attach_research_document(session["id"], document["id"], year)
            sources.append(document)

        self._extract_and_store(session["id"], sources)
        return self.get_session(session["id"]) or {}

    def _rebuild_metrics(self, session_id: str, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        self._extract_and_store(session_id, sources)
        return self.get_session(session_id) or {}

    def _extract_and_store(self, session_id: str, sources: List[Dict[str, Any]]) -> None:
        metrics: List[Dict[str, Any]] = []
        for document in sources:
            year = document.get("research_year") or document.get("year")
            if not year:
                continue
            pages = self.documents.get_pages(document["id"])
            for metric in extract_yanji_cloud_metrics(int(year), pages):
                metric["document_id"] = document["id"]
                metrics.append(metric)
        self.db.replace_research_metrics(session_id, metrics)

    def _scan_candidates(self, session_id: str, sources: List[Dict[str, Any]]) -> None:
        candidates: List[Dict[str, Any]] = []
        for document in sources:
            pages = self.documents.get_pages(document["id"])
            page_texts = {int(item["page"]): item.get("text", "") for item in pages}
            tables = self.documents.get_tables(document["id"])
            candidates.extend(
                scan_tables(
                    document["id"],
                    document["name"],
                    tables,
                    page_texts,
                )
            )
        self.db.replace_research_candidates(session_id, candidates)

    def confirm_candidates(self, session_id: str, ids: List[str]) -> Dict[str, Any]:
        session = self.db.get_research_session(session_id)
        if not session:
            raise KeyError("research session not found")
        chosen = self.db.take_research_candidates(session_id, ids)
        if not chosen:
            detail = self.get_session(session_id) or {}
            return detail
        existing = self.db.list_research_metrics(session_id)
        merged = {(item["metric_key"], item["period"]): item for item in existing}
        for item in chosen:
            key = (item["metric_key"], item["period"])
            merged[key] = {
                "metric_key": item["metric_key"],
                "label": item["label"],
                "unit": item["unit"],
                "period": item["period"],
                "value": item["value"],
                "document_id": item["document_id"],
                "page": item["page"],
                "quote": item["quote"],
                "status": "reviewed",
            }
        self.db.replace_research_metrics(session_id, list(merged.values()))
        return self.get_session(session_id) or {}

    # ------------------------------------------------------------------
    # read model
    # ------------------------------------------------------------------
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.db.get_research_session(session_id)
        if not session:
            return None
        sources = self.db.list_research_documents(session_id)
        metrics = self.db.list_research_metrics(session_id)
        for source in sources:
            source["file_url"] = f"/api/documents/{source['id']}/file"
            source["page_url"] = f"/api/documents/{source['id']}/pages/{{page}}.png"
            source["research_year"] = source.get("research_year") or source.get("year")

        candidates = self.db.list_research_candidates(session_id)
        for candidate in candidates:
            candidate["candidate_id"] = candidate["id"]

        if session["symbol"] == "09899":
            periods = PERIODS
        elif metrics:
            periods = sorted({item["period"] for item in metrics})
        else:
            periods = sorted({item["period"] for item in candidates})

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for metric in metrics:
            grouped.setdefault(metric["metric_key"], []).append(metric)

        if session["symbol"] == "09899":
            ordered_keys = [key for key, _, _ in METRIC_ORDER]
            ordered_keys += [key for key in grouped if key not in ordered_keys]
        else:
            ordered_keys = list(grouped.keys())
        ordered_meta = {key: (label, unit) for key, label, unit in METRIC_ORDER}

        rows = []
        for key in ordered_keys:
            label, unit = ordered_meta.get(key, (key, ""))
            if grouped.get(key):
                label = grouped[key][0]["label"]
                unit = grouped[key][0]["unit"]
            cells = {m["period"]: m for m in grouped.get(key, [])}
            ordered_cells = {
                period: (
                    {
                        **cells[period],
                        "status": cells[period]["status"] or "verified",
                    }
                    if period in cells
                    else {
                        "period": period,
                        "value": None,
                        "status": "missing",
                        "page": None,
                        "quote": "",
                        "document_id": "",
                    }
                )
                for period in periods
            }
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "cells": ordered_cells,
                    "available": sum(1 for cell in ordered_cells.values() if cell["value"] is not None),
                    "missing": [period for period, cell in ordered_cells.items() if cell["value"] is None],
                }
            )

        expected = len(rows) * len(periods)
        available = sum(row["available"] for row in rows)
        candidate_groups = group_candidates(candidates)
        return {
            "id": session["id"],
            "symbol": session["symbol"],
            "name": session["name"],
            "question": session["question"],
            "status": session["status"],
            "created_at": session["created_at"],
            "periods": periods,
            "sources": sources,
            "metrics": rows,
            "candidates": candidate_groups,
            "quality": {
                "available_cells": available,
                "expected_cells": expected,
                "citation_rate": round(available / expected, 3) if expected else 0,
                "missing_cells": max(expected - available, 0),
                "verified_cells": sum(
                    1 for row in rows for cell in row["cells"].values() if cell["value"] is not None
                ),
            },
            "cards": self.db.list_research_cards(session_id),
            "messages": self.db.list_research_messages(session_id),
        }

    def list_sessions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.list_research_sessions(symbol)


    def ask(self, session_id: str, question: str, settings: Settings) -> Dict[str, Any]:
        """Run the research profile for one user question.

        The method only orchestrates persistence and context; the decision
        loop lives in the shared AgentRunner helper.
        """
        detail = self.get_session(session_id)
        if not detail:
            raise KeyError("research session not found")
        question = question.strip()
        if not question:
            raise ValueError("question is required")
        self.db.add_research_message(session_id, "user", question)
        symbol = detail["symbol"]
        market = "cn" if symbol.isdigit() else "us"
        ctx = ToolContext(
            provider=self.provider,
            symbol=symbol,
            as_of=detail["periods"][-1] if detail.get("periods") else "",
            stock={"symbol": symbol, "name": detail["name"], "market": market},
            research=self,
            session_id=session_id,
        )
        result = run_research_agent(
            ctx, question, settings, history=detail.get("messages", [])[-4:]
        )
        data = {
            "citations": result.citations,
            "artifacts": result.artifacts,
            "gaps": result.gaps,
            "trace": result.trace,
            "generated_by": result.generated_by,
            "error": result.error,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }
        message = self.db.add_research_message(session_id, "assistant", result.answer, data)
        return {
            "session_id": session_id,
            "user_message": question,
            "message": message,
            "answer": result.answer,
            "citations": result.citations,
            "artifacts": result.artifacts,
            "gaps": result.gaps,
            "trace": result.trace,
            "generated_by": result.generated_by,
            "error": result.error,
        }


    def ensure_session(self, symbol: str, name: str = "", question: str = "") -> Dict[str, Any]:
        """Return the latest session for a symbol or create an empty one."""
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol is required")
        sessions = self.db.list_research_sessions(symbol)
        if sessions:
            detail = self.get_session(sessions[0]["id"])
            if detail:
                return detail
        if symbol == "09899":
            return self.bootstrap_yanji()
        session = self.db.create_research_session(
            symbol=symbol,
            name=name or symbol,
            question=question or f"{name or symbol} 年报研究",
        )
        return self.get_session(session["id"]) or {}

    def add_document(
        self,
        session_id: str,
        path: Path,
        year: Optional[int] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self.db.get_research_session(session_id)
        if not session:
            raise KeyError("research session not found")
        document = self.documents.ingest_pdf(
            path,
            symbol=session["symbol"],
            year=year,
            name=name or path.name,
        )
        if not document:
            raise ValueError("document ingest failed")
        self.db.attach_research_document(session_id, document["id"], year)
        sources = self.db.list_research_documents(session_id)
        if session["symbol"] == "09899":
            self._extract_and_store(session_id, sources)
        else:
            self._scan_candidates(session_id, sources)
        return self.get_session(session_id) or {}
