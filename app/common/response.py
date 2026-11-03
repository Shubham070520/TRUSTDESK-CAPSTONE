from typing import Any

from fastapi.responses import JSONResponse


class ResponseBuilder:
    """Builds the single response envelope used by every endpoint.

    Success: {"success": true,  "message": "...", "data": ...}
    Error:   {"success": false, "message": "...", "error_code": 1xxx, "data": {}}
    The documented shape of this envelope is ``Envelope`` in ``app.common.schema``.
    """

    def body(
        self,
        success: bool,
        message: str,
        data: Any = None,
        error_code: int | None = None,
    ) -> dict[str, Any]:
        if success:
            return {"success": True, "message": message, "data": data}
        return {
            "success": False,
            "message": message,
            "error_code": error_code,
            "data": data if data is not None else {},
        }

    def json(
        self,
        success: bool,
        message: str,
        data: Any = None,
        error_code: int | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=self.body(success, message, data, error_code),
            headers=headers,
        )
