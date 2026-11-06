"""Application service for uploaded research documents.

The service owns filesystem paths, document persistence and page rendering.
Agent tools call this service; the agent loop itself remains storage-agnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db import Database
from app.documents.parser import PdfParser, ParsedDocument


class DocumentService:
    def __init__(self, db: Database, uploads_dir: Path):
        self.db = db
        self.uploads_dir = Path(uploads_dir)
        self.parser = PdfParser()

    def ingest_pdf(
        self,
        path: Path,
        symbol: str = "",
        year: Optional[int] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = self.parser.parse(path)
        existing = self.db.get_document_by_hash(parsed.sha256)
        if existing:
            return existing

        document_id = f"doc_{parsed.sha256[:12]}"
        pages = [
            {
                "page": page.page,
                "text": page.text,
                "width": page.width,
                "height": page.height,
            }
            for page in parsed.pages
        ]
        self.db.save_document(
            document_id=document_id,
            name=name or parsed.name,
            path=str(path.resolve()),
            page_count=parsed.page_count,
            sha256=parsed.sha256,
            symbol=symbol,
            year=year,
            pages=pages,
        )
        return self.db.get_document(document_id) or {}

    def get_pages(self, document_id: str) -> List[Dict[str, Any]]:
        document = self.db.get_document(document_id)
        if not document:
            return []
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT page, text, width, height FROM document_pages WHERE document_id = ? ORDER BY page",
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_tables(self, document_id: str) -> List[Dict[str, Any]]:
        document = self.db.get_document(document_id)
        if not document:
            return []
        return self.parser.extract_tables(Path(document["path"]))

    def render_page(self, document_id: str, page: int) -> bytes:
        document = self.db.get_document(document_id)
        if not document:
            raise FileNotFoundError("document not found")
        path = Path(document["path"])
        return self.parser.render_page(path, page)

    def file_path(self, document_id: str) -> Path:
        document = self.db.get_document(document_id)
        if not document:
            raise FileNotFoundError("document not found")
        path = Path(document["path"])
        if not path.exists():
            raise FileNotFoundError("document file is missing")
        return path

    def search(self, document_id: str, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        pages = self.get_pages(document_id)
        for page in pages:
            page["document_id"] = document_id
        return self.parser.search(pages, query, limit=limit)
