from http import HTTPStatus
from pathlib import Path
from typing import ClassVar

from fastapi.responses import FileResponse

from app.common.database import Database
from app.common.logger import Logger
from app.urls.base import BaseRouter


class FrontendRouter(BaseRouter):
    """Serves the reviewer page. It holds no data, so it needs no token.

    The page displays untrusted ticket text next to a live token. The header stops
    anything injected into it from loading other content or sending data elsewhere.
    Inline script and style are allowed because the page is one self-contained file.
    """

    _SECURITY_HEADERS: ClassVar[dict[str, str]] = {
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }

    def __init__(self, database: Database, logger: Logger, page: Path, tags: list[str]) -> None:
        super().__init__(database, logger, tags=tags)
        self._page = page

    def register_routes(self) -> None:
        self._router.add_api_route(
            "/",
            self._index,
            methods=["GET"],
            status_code=HTTPStatus.OK,
            response_class=FileResponse,
            include_in_schema=False,
        )

    def _index(self) -> FileResponse:
        return FileResponse(self._page, media_type="text/html", headers=self._SECURITY_HEADERS)
