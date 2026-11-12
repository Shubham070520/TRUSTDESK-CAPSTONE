import logging
from typing import ClassVar


class Logger:
    """Thin wrapper over the standard logger so callers depend on this class."""

    _FORMAT: ClassVar[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    _configured: ClassVar[bool] = False

    def __init__(self, name: str, level: int = logging.INFO) -> None:
        self._configure_root(level)
        self._logger = logging.getLogger(name)

    @classmethod
    def _configure_root(cls, level: int) -> None:
        if not cls._configured:
            logging.basicConfig(level=level, format=cls._FORMAT)
            cls._configured = True

    def info(self, message: str) -> None:
        self._logger.info(message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)

    def error(self, message: str) -> None:
        self._logger.error(message)

    def exception(self, message: str) -> None:
        """Log at error level with the current stack trace."""
        self._logger.exception(message)
