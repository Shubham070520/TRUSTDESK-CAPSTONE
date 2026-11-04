from functools import partial
from typing import Any

from fastapi.responses import JSONResponse

from app.common.document_parser import KnowledgeDocumentParser, ParsedDocument
from app.common.exceptions import ValidationError
from app.common.logger import Logger
from app.common.schema import (
    DocumentIngestData,
    DocumentIngestRequest,
    DocumentIngestResultItem,
    DocumentOut,
    DocumentSearchData,
    DocumentSearchResult,
)
from app.config import Config, SuccessConfig
from app.handler.base import BaseHandler
from app.helper.document import DocumentHelper


class DocumentHandler(BaseHandler):
    def __init__(
        self,
        helper: DocumentHelper,
        parser: KnowledgeDocumentParser,
        logger: Logger,
    ) -> None:
        super().__init__(logger)
        self._helper = helper
        self._parser = parser

    def search(self, query: str, k: int) -> JSONResponse:
        return self.execute(partial(self._search, query, k), SuccessConfig.DOCUMENTS_SEARCHED)

    def get_document(self, doc_id: str) -> JSONResponse:
        return self.execute(partial(self._get, doc_id), SuccessConfig.DOCUMENT_FETCHED)

    def ingest(self, request: DocumentIngestRequest) -> JSONResponse:
        return self.execute(partial(self._ingest, request), SuccessConfig.DOCUMENTS_INGESTED)

    # ---- actions run inside ``execute`` -----------------------------------

    def _search(self, query: str, k: int) -> dict[str, Any]:
        query = self._validate_query(query)
        if not 1 <= k <= Config.MAX_SEARCH_K:
            raise ValidationError(details={"k": k, "max_k": Config.MAX_SEARCH_K})
        hits = self._helper.search(query, k)
        data = DocumentSearchData(
            query=query,
            results=[
                DocumentSearchResult(
                    doc_id=hit.doc_id,
                    title=hit.title,
                    heading=hit.heading,
                    snippet=hit.snippet,
                    score=hit.score,
                    audience=hit.audience,
                )
                for hit in hits
            ],
        )
        return data.model_dump(mode="json")

    def _get(self, doc_id: str) -> dict[str, Any]:
        document = self._helper.get_one(self.validate_identifier(doc_id, "doc_id"))
        return DocumentOut.model_validate(document).model_dump(mode="json")

    def _ingest(self, request: DocumentIngestRequest) -> dict[str, Any]:
        ids = [item.doc_id for item in request.documents]
        duplicates = sorted({doc_id for doc_id in ids if ids.count(doc_id) > 1})
        if duplicates:
            raise ValidationError(details={"duplicate_doc_ids": duplicates})
        parsed: list[ParsedDocument] = [
            self._parser.build(
                doc_id=item.doc_id,
                title=item.title,
                content=item.content,
                source_path=item.source_path or f"api://ingest/{item.doc_id}",
                version=item.version,
                audience=item.audience,
            )
            for item in request.documents
        ]
        results = self._helper.ingest(parsed)
        data = DocumentIngestData(
            ingested=len(results),
            document_ids=[r.doc_id for r in results],
            results=[DocumentIngestResultItem(doc_id=r.doc_id, outcome=r.outcome) for r in results],
        )
        return data.model_dump(mode="json")

    @staticmethod
    def _validate_query(query: str) -> str:
        cleaned = query.strip() if isinstance(query, str) else ""
        if not cleaned or len(cleaned) > Config.MAX_QUERY_LENGTH:
            raise ValidationError(
                details={"q": "required", "max_length": Config.MAX_QUERY_LENGTH}
            )
        return cleaned
