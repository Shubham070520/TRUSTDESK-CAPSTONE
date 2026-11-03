import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.common.exceptions import NotFoundError, ValidationError


@dataclass(frozen=True)
class SourceFile:
    """A text file read from disk, with its path relative to the project root."""

    relative_path: str
    text: str


class DataFileReader:
    """Reads the seed files. Paths are injected so tests can point elsewhere."""

    KNOWLEDGE_DIR = "knowledge_base"
    MARKDOWN_GLOB = "*.md"

    def __init__(self, base_dir: Path, data_dir: Path) -> None:
        self._base_dir = base_dir
        self._data_dir = data_dir

    def read_json(self, file_name: str) -> list[dict[str, Any]]:
        path = self._data_dir / file_name
        rows = json.loads(self._read(path))
        if not isinstance(rows, list):
            raise ValidationError(details={"file": file_name, "expected": "list"})
        return rows

    def read_jsonl(self, file_name: str) -> list[dict[str, Any]]:
        path = self._data_dir / file_name
        rows: list[dict[str, Any]] = []
        for number, line in enumerate(self._read(path).splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValidationError(details={"file": file_name, "line": number}) from exc
        return rows

    def read_knowledge_files(self) -> list[SourceFile]:
        directory = self._data_dir / self.KNOWLEDGE_DIR
        if not directory.is_dir():
            raise NotFoundError(details={"path": str(directory)})
        files: list[SourceFile] = []
        for path in sorted(directory.glob(self.MARKDOWN_GLOB)):
            relative = path.relative_to(self._base_dir).as_posix()
            files.append(SourceFile(relative_path=relative, text=self._read(path)))
        return files

    @staticmethod
    def _read(path: Path) -> str:
        if not path.is_file():
            raise NotFoundError(details={"path": str(path)})
        # Universal newlines: CRLF and LF files produce identical text.
        return path.read_text(encoding="utf-8")
