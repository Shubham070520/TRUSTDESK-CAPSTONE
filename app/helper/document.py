import re
from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.common.document_parser import ParsedDocument
from app.common.exceptions import NotFoundError
from app.helper.base import BaseHelper
from app.models.base import TableNames
from app.models.document import Document


@dataclass(frozen=True)
class SearchHit:
    """The best-matching section of one document. Higher score is better."""

    doc_id: str
    title: str
    heading: str
    snippet: str
    score: float
    audience: str


@dataclass(frozen=True)
class IngestResult:
    doc_id: str
    outcome: str


class DocumentHelper(BaseHelper):
    """Knowledge documents and their FTS5 section index.

    This is the only class that touches the FTS table.
    ``upsert`` flushes but never commits; ``ingest`` commits.
    """

    CREATED: ClassVar[str] = "created"
    UPDATED: ClassVar[str] = "updated"
    UNCHANGED: ClassVar[str] = "unchanged"

    # Words that carry no meaning for ranking. Keeps OR-queries from matching everything.
    _STOPWORDS: ClassVar[frozenset[str]] = frozenset(
        "a an and are as at be but by can do for from has have how i if in is it me my of "
        "on or our so that the their them then there this to us was we what when where "
        "which who will with you your not no all any may must should would could been "
        "being does did also than too very just".split()
    )
    # Matches that score below this are noise (a word found in almost every document).
    _MIN_SCORE: ClassVar[float] = 0.01
    _TOKEN: ClassVar[re.Pattern[str]] = re.compile(r"[A-Za-z0-9]+")
    _MAX_TOKENS: ClassVar[int] = 32
    _SECTIONS_PER_DOCUMENT: ClassVar[int] = 6
    _SNIPPET_WORDS: ClassVar[int] = 24

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self._fts = TableNames.documents_fts()

    # ---- write ------------------------------------------------------------

    def upsert(self, parsed: ParsedDocument) -> str:
        """Insert or update a document by ``doc_id`` and rebuild its search rows."""
        with self._guard():
            existing = self.db.execute(
                select(Document).where(Document.doc_id == parsed.doc_id)
            ).scalar_one_or_none()

            if existing is None:
                outcome = self.CREATED
                document = Document(doc_id=parsed.doc_id)
                self.db.add(document)
            else:
                outcome = (
                    self.UNCHANGED if existing.checksum == parsed.checksum else self.UPDATED
                )
                document = existing

            document.title = parsed.title
            document.content = parsed.content
            document.source_path = parsed.source_path
            document.version = parsed.version
            document.audience = parsed.audience
            document.checksum = parsed.checksum
            document.is_deleted = False

            self._reindex(parsed)
            self.db.flush()
        return outcome

    def ingest(self, documents: list[ParsedDocument]) -> list[IngestResult]:
        """Upsert several documents in one transaction."""
        results: list[IngestResult] = []
        try:
            for parsed in documents:
                results.append(IngestResult(parsed.doc_id, self.upsert(parsed)))
        except Exception:
            self.rollback()
            raise
        self.commit()
        return results

    # ---- read -------------------------------------------------------------

    def count(self) -> int:
        with self._guard():
            return int(self.db.execute(select(func.count(Document.id))).scalar_one())

    def section_count(self) -> int:
        with self._guard():
            return int(
                self.db.execute(text(f"SELECT COUNT(*) FROM {self._fts}")).scalar_one()
            )

    def search(self, query: str, k: int) -> list[SearchHit]:
        """BM25 keyword search. One hit per document (its best section), best first."""
        match = self._build_match(query)
        if match is None:
            return []
        with self._guard():
            rows = self.db.execute(
                text(
                    f"SELECT doc_id, heading, "
                    f"snippet({self._fts}, 3, '', '', ' ... ', {self._SNIPPET_WORDS}) AS snip, "
                    f"bm25({self._fts}) AS rank_score "
                    f"FROM {self._fts} WHERE {self._fts} MATCH :match "
                    f"ORDER BY rank_score LIMIT :limit"
                ),
                {"match": match, "limit": k * self._SECTIONS_PER_DOCUMENT},
            ).all()
            best: dict[str, tuple[str, str, float]] = {}
            for doc_id, heading, snippet, rank_score in rows:
                if doc_id not in best:
                    best[doc_id] = (heading, snippet, float(rank_score))
            documents = self._load_documents(list(best))

        hits: list[SearchHit] = []
        for doc_id, (heading, snippet, rank_score) in best.items():
            document = documents.get(doc_id)
            # bm25() is lower-is-better and negative; flip it so bigger means closer.
            score = round(-rank_score, 4)
            if document is None or score < self._MIN_SCORE:
                continue
            hits.append(
                SearchHit(
                    doc_id=doc_id,
                    title=document.title,
                    heading=heading,
                    snippet=snippet,
                    score=score,
                    audience=document.audience,
                )
            )
            if len(hits) == k:
                break
        return hits

    def get_many(self, doc_ids: list[str]) -> dict[str, Document]:
        """Live documents by ``doc_id``. Ids that do not exist are left out."""
        with self._guard():
            return self._load_documents(doc_ids)

    def get_one(self, doc_id: str) -> Document:
        document = self.get_many([doc_id]).get(doc_id)
        if document is None:
            raise NotFoundError(details={"doc_id": doc_id})
        return document

    # ---- internals --------------------------------------------------------

    def _load_documents(self, doc_ids: list[str]) -> dict[str, Document]:
        if not doc_ids:
            return {}
        rows = self.db.execute(
            select(Document).where(Document.doc_id.in_(doc_ids), Document.is_deleted.is_(False))
        ).scalars()
        return {document.doc_id: document for document in rows}

    def _build_match(self, query: str) -> str | None:
        """Turn free text into a safe FTS5 expression: quoted words joined by OR."""
        tokens: list[str] = []
        for token in self._TOKEN.findall(query.lower()):
            if len(token) < 2 or token in self._STOPWORDS or token in tokens:
                continue
            tokens.append(token)
            if len(tokens) == self._MAX_TOKENS:
                break
        if not tokens:
            return None
        return " OR ".join(f'"{token}"' for token in tokens)

    def _reindex(self, parsed: ParsedDocument) -> None:
        self.db.execute(
            text(f"DELETE FROM {self._fts} WHERE doc_id = :doc_id"),
            {"doc_id": parsed.doc_id},
        )
        for section in parsed.sections:
            self.db.execute(
                text(
                    f"INSERT INTO {self._fts} (doc_id, title, heading, body) "
                    "VALUES (:doc_id, :title, :heading, :body)"
                ),
                {
                    "doc_id": parsed.doc_id,
                    "title": parsed.title,
                    "heading": section.heading,
                    "body": section.body,
                },
            )
