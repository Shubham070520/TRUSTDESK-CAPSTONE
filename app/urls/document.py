from http import HTTPStatus
from typing import Any

from sqlalchemy.orm import Session

from app.common.document_parser import KnowledgeDocumentParser
from app.common.schema import (
    DocumentIngestData,
    DocumentIngestRequest,
    DocumentSearchData,
    Envelope,
)
from app.config import Config
from app.handler.document import DocumentHandler
from app.helper.document import DocumentHelper
from app.urls.base import BaseRouter


class DocumentRouter(BaseRouter):
    def register_routes(self) -> None:
        self._router.add_api_route(
            "/search",
            self._search,
            methods=["GET"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[DocumentSearchData],
            dependencies=self._secured(),
            summary="Ranked keyword search over the knowledge base",
        )
        self._router.add_api_route(
            "/ingest",
            self._ingest,
            methods=["POST"],
            status_code=HTTPStatus.OK,
            response_model=Envelope[DocumentIngestData],
            dependencies=self._secured(),
            summary="Ingest one or more knowledge documents (ids are preserved)",
        )

    def _build_handler(self, db: Session) -> DocumentHandler:
        return DocumentHandler(DocumentHelper(db), KnowledgeDocumentParser(), self._logger)

    def _search(self, q: str = "", k: int = Config.DEFAULT_SEARCH_K) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).search(q, k)

    def _ingest(self, body: DocumentIngestRequest) -> Any:
        with self._database.session_scope() as db:
            return self._build_handler(db).ingest(body)
