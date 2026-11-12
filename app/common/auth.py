import hmac
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.common.exceptions import AuthenticationError
from app.config import Config


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. Reviewer id is recorded on approvals and audits."""

    reviewer_id: str


class AuthDependency:
    """FastAPI dependency that checks the static demo bearer token.

    Used as ``Depends(auth_dependency_instance)`` by routers. Returns the
    ``Principal`` or raises ``AuthenticationError`` (HTTP 401).
    """

    _SCHEME = HTTPBearer(auto_error=False)

    def __init__(self, config: Config) -> None:
        self._expected = config.token.encode("utf-8")
        self._reviewer_id = Config.REVIEWER_ID

    def __call__(
        self,
        credentials: HTTPAuthorizationCredentials | None = Depends(_SCHEME),
    ) -> Principal:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise AuthenticationError()
        supplied = credentials.credentials.encode("utf-8")
        if not hmac.compare_digest(supplied, self._expected):
            raise AuthenticationError()
        return Principal(reviewer_id=self._reviewer_id)
