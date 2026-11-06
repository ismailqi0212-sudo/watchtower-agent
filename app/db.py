"""SQLite persistence layer.

Deliberately plain sqlite3 instead of an ORM: the schema is small, the project
is easy to run, and every query stays visible for debugging and maintenance.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'cn',
    industry TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    trigger TEXT NOT NULL DEFAULT 'manual',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'demo',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'tool',
    tool TEXT NOT NULL DEFAULT '',
    args_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    ok INTEGER NOT NULL DEFAULT 1,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    error TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    score INTEGER NOT NULL,
    confidence REAL NOT NULL,
    data_quality TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    markdown TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_symbol ON runs(symbol, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id, step);
CREATE INDEX IF NOT EXISTS idx_reports_run ON reports(run_id);
CREATE INDEX IF NOT EXISTS idx_reports_symbol ON reports(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_run ON chat_messages(run_id, id);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    year INTEGER,
    path TEXT NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_pages (
    document_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    width REAL NOT NULL DEFAULT 0,
    height REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(document_id, page),
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS research_sessions (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    question TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_documents (
    session_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    year INTEGER,
    PRIMARY KEY(session_id, document_id),
    FOREIGN KEY(session_id) REFERENCES research_sessions(id),
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS research_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    label TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL,
    value REAL,
    document_id TEXT NOT NULL DEFAULT '',
    page INTEGER,
    quote TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'verified',
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(id)
);

CREATE TABLE IF NOT EXISTS research_reports (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    template TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '[]',
    review_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(id)
);

CREATE TABLE IF NOT EXISTS research_report_versions (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    sections_json TEXT NOT NULL DEFAULT '[]',
    review_json TEXT NOT NULL DEFAULT '{}',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(report_id, version),
    FOREIGN KEY(report_id) REFERENCES research_reports(id)
);

CREATE TABLE IF NOT EXISTS research_candidates (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    label TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL,
    value REAL,
    document_id TEXT NOT NULL DEFAULT '',
    document_name TEXT NOT NULL DEFAULT '',
    page INTEGER,
    quote TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(id)
);

CREATE TABLE IF NOT EXISTS research_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(id)
);

CREATE TABLE IF NOT EXISTS research_cards (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL DEFAULT '{}',
    selected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_symbol ON documents(symbol, year);
CREATE INDEX IF NOT EXISTS idx_research_metrics_session ON research_metrics(session_id, metric_key, period);
CREATE INDEX IF NOT EXISTS idx_research_cards_session ON research_cards(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_research_messages_session ON research_messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_research_candidates_session ON research_candidates(session_id, metric_key);
CREATE INDEX IF NOT EXISTS idx_research_reports_session ON research_reports(session_id, created_at DESC);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(research_reports)").fetchall()
            }
            if "version" not in columns:
                conn.execute(
                    "ALTER TABLE research_reports ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
                )

    # ------------------------------------------------------------------
    # stocks
    # ------------------------------------------------------------------
    def add_stock(
        self, symbol: str, name: str, market: str = "cn", industry: str = ""
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO stocks(symbol, name, market, industry, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name=excluded.name,
                    market=excluded.market,
                    industry=excluded.industry
                """,
                (symbol, name, market, industry, utc_now()),
            )

    def remove_stock(self, symbol: str) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))

    def get_stock(self, symbol: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM stocks WHERE symbol = ?", (symbol,)
            ).fetchone()
        return dict(row) if row else None

    def list_stocks(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM stocks ORDER BY created_at ASC").fetchall()
        return [dict(row) for row in rows]

    def count_stocks(self) -> int:
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM stocks").fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------
    def create_run(
        self, symbol: str, mode: str, model: str, trigger: str = "manual"
    ) -> Dict[str, Any]:
        run_id = new_id("run")
        started = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO runs(id, symbol, status, trigger, started_at, model, mode)
                VALUES (?, ?, 'running', ?, ?, ?, ?)
                """,
                (run_id, symbol, trigger, started, model, mode),
            )
        return {
            "id": run_id,
            "symbol": symbol,
            "status": "running",
            "trigger": trigger,
            "started_at": started,
            "model": model,
            "mode": mode,
        }

    def finish_run(
        self,
        run_id: str,
        status: str,
        latency_ms: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, latency_ms = ?,
                    prompt_tokens = ?, completion_tokens = ?, cost_usd = ?, error = ?
                WHERE id = ?
                """,
                (
                    status,
                    utc_now(),
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    error,
                    run_id,
                ),
            )

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(
        self, symbol: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE symbol = ? ORDER BY started_at DESC LIMIT ?",
                    (symbol, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # traces
    # ------------------------------------------------------------------
    def add_trace(
        self,
        run_id: str,
        step: int,
        kind: str,
        tool: str = "",
        args: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        ok: bool = True,
        latency_ms: int = 0,
        summary: str = "",
        error: Optional[str] = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO tool_calls(run_id, step, kind, tool, args_json,
                                       result_json, ok, latency_ms, summary, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    step,
                    kind,
                    tool,
                    _json(args or {}),
                    _json(result or {}),
                    1 if ok else 0,
                    latency_ms,
                    summary,
                    error,
                ),
            )

    def list_traces(self, run_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY step ASC, id ASC",
                (run_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["args"] = json.loads(item.pop("args_json") or "{}")
            item["result"] = json.loads(item.pop("result_json") or "{}")
            item["ok"] = bool(item["ok"])
            result.append(item)
        return result

    # ------------------------------------------------------------------
    # reports
    # ------------------------------------------------------------------
    def save_report(
        self,
        run_id: str,
        symbol: str,
        report: Dict[str, Any],
        markdown: str = "",
    ) -> Dict[str, Any]:
        report_id = new_id("rep")
        created = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO reports(id, run_id, symbol, action, score, confidence,
                                    data_quality, payload_json, markdown, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    run_id,
                    symbol,
                    report.get("action", "watch"),
                    int(report.get("score", 50)),
                    float(report.get("confidence", 0.5)),
                    report.get("data_quality", "ok"),
                    _json(report),
                    markdown,
                    created,
                ),
            )
        return {
            "id": report_id,
            "run_id": run_id,
            "symbol": symbol,
            "created_at": created,
            **report,
        }

    def get_report_by_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        payload = json.loads(item.pop("payload_json"))
        item.update(payload)
        item["markdown"] = item.get("markdown", "")
        return item

    def latest_report(self, symbol: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        payload = json.loads(item.pop("payload_json"))
        item.update(payload)
        item["markdown"] = item.get("markdown", "")
        return item

    def list_reports(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item.pop("payload_json"))
            item.update(payload)
            item["markdown"] = item.get("markdown", "")
            items.append(item)
        return items

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------
    def add_chat(self, run_id: str, role: str, content: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO chat_messages(run_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (run_id, role, content, utc_now()),
            )

    def list_chat(self, run_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # research documents / metrics
    # ------------------------------------------------------------------
    def save_document(
        self,
        document_id: str,
        name: str,
        path: str,
        page_count: int,
        sha256: str,
        symbol: str = "",
        year: Optional[int] = None,
        pages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO documents(id, symbol, name, year, path, page_count, sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, path=excluded.path, page_count=excluded.page_count,
                    sha256=excluded.sha256, symbol=excluded.symbol, year=excluded.year
                """,
                (document_id, symbol, name, year, path, page_count, sha256, utc_now()),
            )
            if pages:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO document_pages(document_id, page, text, width, height)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (document_id, int(p["page"]), p.get("text", ""), float(p.get("width", 0)), float(p.get("height", 0)))
                        for p in pages
                    ],
                )

    def get_document_by_hash(self, sha256: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE sha256 = ? LIMIT 1", (sha256,)).fetchone()
        return dict(row) if row else None

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE symbol = ? ORDER BY year ASC, created_at ASC",
                    (symbol,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM documents ORDER BY year ASC, created_at ASC").fetchall()
        return [dict(row) for row in rows]

    def get_document_page(self, document_id: str, page: int) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM document_pages WHERE document_id = ? AND page = ?",
                (document_id, page),
            ).fetchone()
        return dict(row) if row else None

    def create_research_session(
        self, symbol: str, name: str, question: str = ""
    ) -> Dict[str, Any]:
        session_id = new_id("res")
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO research_sessions(id, symbol, name, question, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ready', ?, ?)
                """,
                (session_id, symbol, name, question, now, now),
            )
        return self.get_research_session(session_id) or {}

    def get_research_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def list_research_sessions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM research_sessions WHERE symbol = ? ORDER BY updated_at DESC",
                    (symbol,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM research_sessions ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def attach_research_document(self, session_id: str, document_id: str, year: Optional[int]) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_documents(session_id, document_id, year)
                VALUES (?, ?, ?)
                """,
                (session_id, document_id, year),
            )

    def list_research_documents(self, session_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT d.*, rd.year AS research_year
                FROM research_documents rd
                JOIN documents d ON d.id = rd.document_id
                WHERE rd.session_id = ?
                ORDER BY rd.year ASC
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_research_metrics(self, session_id: str, metrics: List[Dict[str, Any]]) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM research_metrics WHERE session_id = ?", (session_id,))
            conn.executemany(
                """
                INSERT INTO research_metrics(
                    session_id, metric_key, label, unit, period, value,
                    document_id, page, quote, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        item["metric_key"],
                        item["label"],
                        item.get("unit", ""),
                        item["period"],
                        item.get("value"),
                        item.get("document_id", ""),
                        item.get("page"),
                        item.get("quote", ""),
                        item.get("status", "verified"),
                        utc_now(),
                    )
                    for item in metrics
                ],
            )

    def list_research_metrics(self, session_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_metrics WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_research_cards(self, session_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_cards WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item.pop("data_json") or "{}")
            item["selected"] = bool(item["selected"])
            items.append(item)
        return items


    def add_research_message(
        self, session_id: str, role: str, content: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO research_messages(session_id, role, content, data_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, json.dumps(data or {}, ensure_ascii=False, default=str), utc_now()),
            )
            message_id = cursor.lastrowid
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "data": data or {},
            "created_at": utc_now(),
        }

    def list_research_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item.pop("data_json") or "{}")
            items.append(item)
        return items


    def replace_research_candidates(self, session_id: str, candidates: List[Dict[str, Any]]) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM research_candidates WHERE session_id = ?", (session_id,))
            conn.executemany(
                """
                INSERT OR REPLACE INTO research_candidates(
                    id, session_id, metric_key, label, unit, period, value,
                    document_id, document_name, page, quote, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)
                """,
                [
                    (
                        item["candidate_id"],
                        session_id,
                        item["metric_key"],
                        item["label"],
                        item.get("unit", ""),
                        item["period"],
                        item.get("value"),
                        item.get("document_id", ""),
                        item.get("document_name", ""),
                        item.get("page"),
                        item.get("quote", ""),
                        utc_now(),
                    )
                    for item in candidates
                ],
            )

    def list_research_candidates(self, session_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_candidates WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def take_research_candidates(self, session_id: str, ids: List[str]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM research_candidates WHERE session_id = ? AND id IN ({marks})",
                [session_id, *ids],
            ).fetchall()
            conn.execute(
                f"DELETE FROM research_candidates WHERE session_id = ? AND id IN ({marks})",
                [session_id, *ids],
            )
        return [dict(row) for row in rows]


    def save_research_report(
        self,
        session_id: str,
        title: str,
        template: str,
        sections: List[Dict[str, Any]],
        review: Dict[str, Any],
    ) -> Dict[str, Any]:
        report_id = new_id("resrep")
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO research_reports(id, session_id, title, template, content_json, review_json, version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    report_id,
                    session_id,
                    title,
                    template,
                    json.dumps(sections, ensure_ascii=False, default=str),
                    json.dumps(review, ensure_ascii=False, default=str),
                    now,
                    now,
                ),
            )
            self._insert_report_version(conn, report_id, 1, title, sections, review, "生成", now)
        return self.get_research_report(report_id) or {}

    def _insert_report_version(
        self,
        conn: Any,
        report_id: str,
        version: int,
        title: str,
        sections: List[Dict[str, Any]],
        review: Dict[str, Any],
        note: str,
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_report_versions(
                id, report_id, version, title, sections_json, review_json, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("resver"),
                report_id,
                version,
                title,
                json.dumps(sections, ensure_ascii=False, default=str),
                json.dumps(review, ensure_ascii=False, default=str),
                note,
                now,
            ),
        )

    def update_research_report(
        self,
        report_id: str,
        title: str,
        sections: List[Dict[str, Any]],
        review: Dict[str, Any],
        note: str = "人工编辑",
    ) -> Optional[Dict[str, Any]]:
        current = self.get_research_report(report_id)
        if not current:
            return None
        version = int(current.get("version") or 1) + 1
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE research_reports
                SET title = ?, content_json = ?, review_json = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    json.dumps(sections, ensure_ascii=False, default=str),
                    json.dumps(review, ensure_ascii=False, default=str),
                    version,
                    now,
                    report_id,
                ),
            )
            self._insert_report_version(conn, report_id, version, title, sections, review, note, now)
        return self.get_research_report(report_id)

    def list_report_versions(self, report_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, report_id, version, title, review_json, note, created_at FROM research_report_versions WHERE report_id = ? ORDER BY version DESC",
                (report_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["review"] = json.loads(item.pop("review_json") or "{}")
            result.append(item)
        return result

    def get_report_version(self, report_id: str, version: int) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM research_report_versions WHERE report_id = ? AND version = ?",
                (report_id, version),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["sections"] = json.loads(item.pop("sections_json") or "[]")
        item["review"] = json.loads(item.pop("review_json") or "{}")
        return item

    def get_research_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM research_reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["sections"] = json.loads(item.pop("content_json") or "[]")
        item["review"] = json.loads(item.pop("review_json") or "{}")
        return item

    def list_research_reports(self, session_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, session_id, title, template, review_json, version, created_at, updated_at FROM research_reports WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["review"] = json.loads(item.pop("review_json") or "{}")
            result.append(item)
        return result
