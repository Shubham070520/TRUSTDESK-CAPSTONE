import re
from pathlib import Path

from app import Application
from app.config import Config, ErrorCode, ErrorConfig
from tests.base import ApiTestCase

BASE = Path(Config.BASE_DIR)
README = (BASE / "README.md").read_text(encoding="utf-8")


class TestReadmeMatchesTheApp(ApiTestCase):
    """The README is the API's documentation, so it fails the build when it drifts."""

    def test_route_table_lists_exactly_the_real_routes(self, application: Application) -> None:
        documented = set(re.findall(r"^\| (GET|POST) \| `(/[^`]*)` \|", README, flags=re.MULTILINE))
        real = {("GET", "/")}  # The page is deliberately left out of the API schema.
        for path, operations in application.create_app().openapi()["paths"].items():
            real.update((method.upper(), path) for method in operations)
        assert documented == real

    def test_every_error_code_is_documented_with_its_status(self) -> None:
        for code in ErrorCode:
            assert f"| {int(code)} | {ErrorConfig.status(code)} |" in README, code.name

    def test_every_env_var_is_documented(self) -> None:
        example = (BASE / ".env.example").read_text(encoding="utf-8")
        names = re.findall(r"^([A-Z_]+)=", example, flags=re.MULTILINE)
        assert names
        for name in names:
            assert f"`{name}`" in README, name

    def test_commands_name_the_real_entry_points(self) -> None:
        assert "uvicorn run:app" in README
        assert "app.main" not in README
        for module in ("seed", "evals"):
            assert f"python -m app.{module}" in README
            assert (BASE / "app" / f"{module}.py").exists()

    def test_requirements_are_pinned(self) -> None:
        lines = (BASE / "requirements.txt").read_text(encoding="utf-8").split()
        assert lines
        for line in lines:
            assert re.fullmatch(r"[a-z-]+==[0-9.]+", line), line
