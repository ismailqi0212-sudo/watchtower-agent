"""PDF ingestion and page rendering.

This module is deliberately below the Agent layer: tools and services use it,
the agent loop never imports PyMuPDF or touches the filesystem directly.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf


@dataclass
class ParsedPage:
    page: int
    text: str
    width: float = 0.0
    height: float = 0.0


@dataclass
class ParsedDocument:
    name: str
    path: str
    sha256: str
    pages: List[ParsedPage] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class PdfParser:
    """Parse text pages from a PDF without OCR.

    The current product scope is text-based annual reports. Scanned PDFs are
    reported as empty pages rather than pretending OCR succeeded.
    """

    def parse(self, path: Path) -> ParsedDocument:
        if not path.exists():
            raise FileNotFoundError(str(path))
        if path.suffix.lower() != ".pdf":
            raise ValueError("only PDF files are supported")
        doc = pymupdf.open(str(path))
        try:
            pages: List[ParsedPage] = []
            for index, page in enumerate(doc):
                text = page.get_text("text") or ""
                rect = page.rect
                pages.append(
                    ParsedPage(
                        page=index + 1,
                        text=text,
                        width=float(rect.width),
                        height=float(rect.height),
                    )
                )
            return ParsedDocument(
                name=path.name,
                path=str(path),
                sha256=file_sha256(path),
                pages=pages,
            )
        finally:
            doc.close()

    def extract_tables(self, path: Path) -> List[Dict[str, Any]]:
        """Return table rows with physical page numbers. Best effort only."""
        doc = pymupdf.open(str(path))
        try:
            output: List[Dict[str, Any]] = []
            for index, page in enumerate(doc):
                try:
                    tables = page.find_tables()
                except Exception:
                    continue
                for table in tables.tables:
                    try:
                        rows = table.extract()
                    except Exception:
                        continue
                    cleaned = []
                    for row in rows:
                        cleaned.append(
                            [
                                re.sub(r"\s+", " ", str(cell)).strip() if cell is not None else ""
                                for cell in row
                            ]
                        )
                    if cleaned:
                        output.append({"page": index + 1, "rows": cleaned})
            return output
        finally:
            doc.close()

    def render_page(self, path: Path, page_number: int, zoom: float = 1.6) -> bytes:
        doc = pymupdf.open(str(path))
        try:
            if page_number < 1 or page_number > doc.page_count:
                raise IndexError("page out of range")
            page = doc[page_number - 1]
            matrix = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            return pix.tobytes("png")
        finally:
            doc.close()

    def search(self, pages: List[Dict[str, Any]], query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Simple page-level keyword search used by research tools.

        This is intentionally deterministic and page-scoped. A later hybrid
        retriever can replace it without changing the tool contract.
        """
        terms = [term.strip().lower() for term in query.split() if term.strip()]
        if not terms:
            return []
        scored = []
        for page in pages:
            text = (page.get("text") or "").lower()
            score = sum(text.count(term) for term in terms)
            if score:
                scored.append((score, page))
        scored.sort(key=lambda item: (-item[0], item[1].get("page", 0)))
        return [
            {
                "document_id": page.get("document_id", ""),
                "page": page.get("page"),
                "text": page.get("text", "")[:1200],
                "score": score,
            }
            for score, page in scored[:limit]
        ]
