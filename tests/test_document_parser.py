import pytest

from app.common.data_reader import DataFileReader
from app.common.document_parser import KnowledgeDocumentParser
from app.common.exceptions import ValidationError
from app.config import Config

SAMPLE = (
    "# Sample Policy\r\n\r\n"
    "Doc ID: KB-SAMPLE-001\r\n"
    "Audience: Agents\r\n"
    "Version: 2026.07\r\n\r\n"
    "## First\r\n\r\nFirst body.\r\n\r\n"
    "## Second\r\n\r\nSecond body line one.\r\nLine two.\r\n"
)


class TestKnowledgeDocumentParser:
    @pytest.fixture()
    def parser(self) -> KnowledgeDocumentParser:
        return KnowledgeDocumentParser()

    def test_parses_header_fields(self, parser: KnowledgeDocumentParser) -> None:
        doc = parser.parse(SAMPLE, "data/knowledge_base/sample.md")
        assert doc.doc_id == "KB-SAMPLE-001"
        assert doc.title == "Sample Policy"
        assert doc.audience == "Agents"
        assert doc.version == "2026.07"
        assert doc.source_path == "data/knowledge_base/sample.md"

    def test_splits_sections_on_h2(self, parser: KnowledgeDocumentParser) -> None:
        doc = parser.parse(SAMPLE, "x.md")
        assert [s.heading for s in doc.sections] == ["First", "Second"]
        assert doc.sections[0].body == "First body."
        assert doc.sections[1].body == "Second body line one.\nLine two."

    def test_crlf_and_lf_give_same_checksum(self, parser: KnowledgeDocumentParser) -> None:
        a = parser.parse(SAMPLE, "x.md")
        b = parser.parse(SAMPLE.replace("\r\n", "\n"), "x.md")
        assert a.checksum == b.checksum
        assert "\r" not in a.content

    def test_document_without_sections_gets_one(self, parser: KnowledgeDocumentParser) -> None:
        text = "# Tiny\n\nDoc ID: KB-TINY-001\nAudience: A\nVersion: 1\n\nJust a body."
        doc = parser.parse(text, "x.md")
        assert len(doc.sections) == 1
        assert doc.sections[0].heading == "Tiny"
        assert "Just a body." in doc.sections[0].body

    @pytest.mark.parametrize(
        "text,missing",
        [
            ("# T\n\nAudience: A\nVersion: 1\n", "doc id"),
            ("# T\n\nDoc ID: X\nVersion: 1\n", "audience"),
            ("# T\n\nDoc ID: X\nAudience: A\n", "version"),
            ("Doc ID: X\nAudience: A\nVersion: 1\n", "title"),
        ],
    )
    def test_missing_required_field(
        self, parser: KnowledgeDocumentParser, text: str, missing: str
    ) -> None:
        with pytest.raises(ValidationError) as info:
            parser.parse(text, "bad.md")
        assert missing in info.value.details["missing"]


class TestRealKnowledgeBase:
    def test_all_provided_documents_parse_with_unique_ids(self) -> None:
        reader = DataFileReader(Config.BASE_DIR, Config.DATA_DIR)
        parser = KnowledgeDocumentParser()
        docs = [parser.parse(f.text, f.relative_path) for f in reader.read_knowledge_files()]
        ids = [d.doc_id for d in docs]
        assert len(ids) == 8
        assert len(set(ids)) == len(ids)
        assert {
            "KB-REFUND-001",
            "KB-SHIPPING-001",
            "KB-WARRANTY-001",
            "KB-ACCOUNT-001",
            "KB-BILLING-001",
            "KB-COUPON-001",
            "KB-SECURITY-001",
            "KB-ADVERSARIAL-001",
        } == set(ids)
        assert all(d.sections for d in docs)
