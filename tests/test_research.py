from pathlib import Path

import pytest

from app.db import Database
from app.documents.parser import PdfParser
from app.documents.service import DocumentService
from app.documents.yanji import extract_yanji_cloud_metrics
from app.services.research import ResearchService

UPLOADS = Path(__file__).resolve().parent.parent / "data" / "uploads"
PDFS = [UPLOADS / f"{year}.pdf" for year in (2021, 2022, 2023, 2024)]

pytestmark = pytest.mark.skipif(
    not all(path.exists() for path in PDFS),
    reason="sample annual reports are not present",
)


def test_extracts_business_and_financial_metrics_with_pages():
    document = PdfParser().parse(UPLOADS / "2023.pdf")
    pages = [{"page": page.page, "text": page.text} for page in document.pages]
    metrics = {item["metric_key"]: item for item in extract_yanji_cloud_metrics(2023, pages)}

    assert metrics["online_paying_users"]["value"] == 44120.0
    assert metrics["online_paying_users"]["page"] == 7
    assert metrics["online_arpu"]["value"] == 6.9
    assert metrics["revenue"]["value"] == 7866.992
    assert metrics["operating_cash_flow"]["value"] == 189.053


def test_bootstrap_builds_a_four_year_read_model(tmp_path):
    db = Database(tmp_path / "research.db")
    db.init_schema()
    service = ResearchService(db, DocumentService(db, UPLOADS))
    detail = service.bootstrap_yanji()

    assert detail["symbol"] == "09899"
    assert len(detail["sources"]) == 4
    assert detail["quality"]["available_cells"] == 35
    assert detail["quality"]["missing_cells"] == 5

    revenue = next(row for row in detail["metrics"] if row["key"] == "revenue")
    assert revenue["cells"]["2024"]["value"] == 7950.146
    assert revenue["cells"]["2024"]["page"] == 5

    paying = next(row for row in detail["metrics"] if row["key"] == "online_paying_users")
    assert paying["cells"]["2023"]["value"] == 44120.0
    assert paying["cells"]["2024"]["status"] == "missing"
    assert paying["cells"]["2024"]["value"] is None


def test_research_ask_fallback_persists_messages(tmp_path):
    from app.config import Settings

    db = Database(tmp_path / "research_ask.db")
    db.init_schema()
    service = ResearchService(db, DocumentService(db, UPLOADS))
    detail = service.bootstrap_yanji()
    settings = Settings(db_path=tmp_path / "research_ask.db", llm_api_key="")
    result = service.ask(detail["id"], "2021–2024 付费用户怎么变？", settings)

    assert result["generated_by"] == "demo-research"
    assert result["answer"]
    assert result["citations"]
    assert result["artifacts"]
    messages = service.get_session(detail["id"])["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"].startswith("2021")


def test_generic_upload_scans_and_confirms_candidates(tmp_path):
    db = Database(tmp_path / "research_generic.db")
    db.init_schema()
    service = ResearchService(db, DocumentService(db, UPLOADS))
    session = service.ensure_session("MSFT", "Microsoft")
    detail = service.add_document(
        session["id"], UPLOADS / "2024.pdf", year=2024, name="2024 年度报告"
    )

    groups = {group["label"]: group for group in detail["candidates"]}
    assert "收入" in groups
    assert "毛利" in groups
    ids = [
        cell["candidate_id"]
        for label in ("收入", "毛利")
        for cell in groups[label]["cells"].values()
    ]

    confirmed = service.confirm_candidates(session["id"], ids)
    labels = {row["label"] for row in confirmed["metrics"]}
    assert {"收入", "毛利"} <= labels
    revenue = next(row for row in confirmed["metrics"] if row["label"] == "收入")
    assert revenue["cells"]["2024"]["value"] == 7950146.0
    assert revenue["cells"]["2024"]["page"] == 5


def test_research_report_assembly_and_markdown(tmp_path):
    from app.services.research_reports import ResearchReportService

    db = Database(tmp_path / "research_report.db")
    db.init_schema()
    research = ResearchService(db, DocumentService(db, UPLOADS))
    detail = research.bootstrap_yanji()
    reports = ResearchReportService(db, research)
    report = reports.generate(
        detail["id"],
        template="full",
        metric_keys=["revenue", "gross_margin", "online_paying_users"],
        title="测试研究",
    )

    assert report["title"] == "测试研究"
    assert report["review"]["metrics"] == 3
    assert report["review"]["citations"] > 0
    assert any(section["kind"] == "metric_table" for section in report["sections"])
    markdown = reports.markdown(report)
    assert "# 测试研究" in markdown
    assert "经营数据" in markdown


def test_research_report_versions_and_edit(tmp_path):
    from app.config import Settings
    from app.services.research_reports import ResearchReportService

    db = Database(tmp_path / "research_versions.db")
    db.init_schema()
    research = ResearchService(db, DocumentService(db, UPLOADS))
    detail = research.bootstrap_yanji()
    reports = ResearchReportService(db, research)
    report = reports.generate(detail["id"], template="full", metric_keys=["revenue"])

    updated = reports.update(report["id"], "人工标题", report["sections"], "人工编辑")
    assert updated["version"] == 2
    assert updated["title"] == "人工标题"
    assert updated["review"]["edited"] is True

    versions = reports.versions(report["id"])
    assert [item["version"] for item in versions] == [2, 1]
    restored = reports.restore(report["id"], 1)
    assert restored["version"] == 3
    assert restored["title"] == report["title"]

    settings = Settings(db_path=tmp_path / "research_versions.db", llm_api_key="")
    with pytest.raises(ValueError):
        reports.polish(report["id"], settings)


def test_report_can_be_assembled_from_snippets(tmp_path):
    from app.services.research_reports import ResearchReportService

    db = Database(tmp_path / "research_snippets.db")
    db.init_schema()
    research = ResearchService(db, DocumentService(db, UPLOADS))
    detail = research.bootstrap_yanji()
    reports = ResearchReportService(db, research)
    report = reports.generate(
        detail["id"],
        template="brief",
        snippets=[
            {"kind": "text", "title": "研究摘录", "body": "2021–2023 付费用户持续增长。", "citations": []},
            {
                "kind": "metric_table",
                "title": "付费用户",
                "metric_keys": ["online_paying_users"],
                "citations": [],
            },
        ],
        title="片段拼装",
    )

    assert report["title"] == "片段拼装"
    assert [section["kind"] for section in report["sections"]][:2] == ["text", "metric_table"]
    table = next(section for section in report["sections"] if section["kind"] == "metric_table")
    assert table["rows"][0]["label"] == "在线音乐月付费用户"
    assert table["citations"]
