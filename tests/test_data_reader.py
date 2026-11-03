from pathlib import Path

import pytest

from app.common.data_reader import DataFileReader
from app.common.exceptions import NotFoundError, ValidationError


class TestDataFileReader:
    @pytest.fixture()
    def reader(self, tmp_path: Path) -> DataFileReader:
        return DataFileReader(tmp_path, tmp_path / "data")

    @pytest.fixture()
    def data_dir(self, tmp_path: Path) -> Path:
        directory = tmp_path / "data"
        directory.mkdir()
        return directory

    def test_read_json(self, reader: DataFileReader, data_dir: Path) -> None:
        (data_dir / "a.json").write_text('[{"x": 1}]', encoding="utf-8")
        assert reader.read_json("a.json") == [{"x": 1}]

    def test_read_json_rejects_non_list(self, reader: DataFileReader, data_dir: Path) -> None:
        (data_dir / "a.json").write_text('{"x": 1}', encoding="utf-8")
        with pytest.raises(ValidationError):
            reader.read_json("a.json")

    def test_read_jsonl_skips_blank_lines(self, reader: DataFileReader, data_dir: Path) -> None:
        (data_dir / "a.jsonl").write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
        assert reader.read_jsonl("a.jsonl") == [{"a": 1}, {"a": 2}]

    def test_read_jsonl_reports_bad_line(self, reader: DataFileReader, data_dir: Path) -> None:
        (data_dir / "a.jsonl").write_text('{"a": 1}\nnot json\n', encoding="utf-8")
        with pytest.raises(ValidationError) as info:
            reader.read_jsonl("a.jsonl")
        assert info.value.details["line"] == 2

    def test_missing_file(self, reader: DataFileReader, data_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            reader.read_json("nope.json")

    def test_knowledge_files_sorted_with_relative_paths(
        self, reader: DataFileReader, data_dir: Path
    ) -> None:
        kb = data_dir / "knowledge_base"
        kb.mkdir()
        (kb / "b.md").write_text("b", encoding="utf-8")
        (kb / "a.md").write_text("a", encoding="utf-8")
        (kb / "ignore.txt").write_text("x", encoding="utf-8")
        files = reader.read_knowledge_files()
        assert [f.relative_path for f in files] == [
            "data/knowledge_base/a.md",
            "data/knowledge_base/b.md",
        ]

    def test_missing_knowledge_dir(self, reader: DataFileReader, data_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            reader.read_knowledge_files()
