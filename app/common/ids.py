import re
from typing import Any, ClassVar
from uuid import UUID, uuid4


class UuidGenerator:
    """Callable column default that produces a new UUID4 string."""

    def __call__(self, context: Any = None) -> str:
        return str(uuid4())


class UuidChecker:
    """Validates the public identifier format."""

    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    @classmethod
    def is_valid(cls, value: str) -> bool:
        if not isinstance(value, str) or not cls._PATTERN.match(value):
            return False
        try:
            UUID(value)
        except ValueError:
            return False
        return True
