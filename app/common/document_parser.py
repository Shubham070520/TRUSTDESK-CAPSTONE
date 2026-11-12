import hashlib
import re
from dataclasses import dataclass, field
from typing import ClassVar

from app.common.exceptions import ValidationError


@dataclass(frozen=True)
class ParsedSection:
    heading: str
    body: str


@dataclass(frozen=True)
class ParsedDocument:
    doc_id: str
    title: str
    version: str
    audience: str
    content: str
    source_path: str
    checksum: str
    sections: list[ParsedSection] = field(default_factory=list)


class KnowledgeDocumentParser:
    """Turns knowledge-base text into a ``ParsedDocument``.

    ``parse`` reads a Markdown file whose header carries the metadata::

        # Title

        Doc ID: KB-XXXX-001
        Audience: ...
        Version: ...

        ## Section heading
        body...

    ``build`` takes the metadata as arguments (used by API ingestion).
    """

    _TITLE: ClassVar[re.Pattern[str]] = re.compile(r"^#\s+(?P<title>.+?)\s*$")
    _SECTION: ClassVar[re.Pattern[str]] = re.compile(r"^##\s+(?P<heading>.+?)\s*$")
    _META: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<key>Doc ID|Audience|Version):\s*(?P<value>.+?)\s*$", re.IGNORECASE
    )
    _REQUIRED: ClassVar[tuple[str, ...]] = ("doc id", "audience", "version")

    def parse(self, text: str, source_path: str) -> ParsedDocument:
        normalized = self._normalize(text)
        preamble, sections = self._split_sections(normalized.split("\n"))
        title, meta = self._read_header(preamble)

        missing = [key for key in self._REQUIRED if key not in meta]
        if title is None:
            missing.insert(0, "title")
        if missing:
            raise ValidationError(details={"file": source_path, "missing": missing})
        assert title is not None

        if not sections:
            sections = [ParsedSection(heading=title, body="\n".join(preamble).strip())]

        return ParsedDocument(
            doc_id=meta["doc id"],
            title=title,
            version=meta["version"],
            audience=meta["audience"],
            content=normalized,
            source_path=source_path,
            checksum=self._checksum(normalized),
            sections=sections,
        )

    def build(
        self,
        doc_id: str,
        title: str,
        content: str,
        source_path: str,
        version: str,
        audience: str,
    ) -> ParsedDocument:
        """Build a document from explicit metadata plus Markdown/plain content."""
        normalized = self._normalize(content)
        preamble, sections = self._split_sections(normalized.split("\n"))
        if not sections:
            sections = [ParsedSection(heading=title, body=normalized.strip())]
        elif "\n".join(preamble).strip():
            sections.insert(0, ParsedSection(heading=title, body="\n".join(preamble).strip()))
        return ParsedDocument(
            doc_id=doc_id,
            title=title,
            version=version,
            audience=audience,
            content=normalized,
            source_path=source_path,
            checksum=self._checksum(normalized),
            sections=sections,
        )

    # ---- internals --------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _checksum(normalized: str) -> str:
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _split_sections(self, lines: list[str]) -> tuple[list[str], list[ParsedSection]]:
        """Return the lines before the first ``##`` heading, and the sections."""
        preamble: list[str] = []
        sections: list[ParsedSection] = []
        heading: str | None = None
        buffer: list[str] = []
        for line in lines:
            match = self._SECTION.match(line)
            if match:
                self._close_section(sections, heading, buffer)
                heading, buffer = match.group("heading"), []
            elif heading is not None:
                buffer.append(line)
            else:
                preamble.append(line)
        self._close_section(sections, heading, buffer)
        return preamble, sections

    def _read_header(self, preamble: list[str]) -> tuple[str | None, dict[str, str]]:
        title: str | None = None
        meta: dict[str, str] = {}
        for line in preamble:
            title_match = self._TITLE.match(line)
            if title_match and title is None:
                title = title_match.group("title")
                continue
            meta_match = self._META.match(line)
            if meta_match:
                meta[meta_match.group("key").lower()] = meta_match.group("value")
        return title, meta

    @staticmethod
    def _close_section(
        sections: list[ParsedSection], heading: str | None, buffer: list[str]
    ) -> None:
        if heading is not None:
            sections.append(ParsedSection(heading=heading, body="\n".join(buffer).strip()))
