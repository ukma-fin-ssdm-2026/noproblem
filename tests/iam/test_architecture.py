"""Архітектурні тести: межа між бізнес-логікою та фреймворком.

Критерій 4 огляду коду Лаб 5 перевіряє, що бізнес-логіка не
переплетена з фреймворком. Домовленість, яку перевіряє лише людина,
рано чи пізно порушать, тому тут її перевіряє CI. Тест розбирає
імпорти кожного файлу через модуль ``ast``, без запуску коду.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

IAM_ROOT = Path(__file__).resolve().parents[2] / "src" / "iam"
FRAMEWORKS = {"fastapi", "starlette", "pydantic", "uvicorn", "sqlalchemy"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def python_files(folder: str) -> list[Path]:
    return sorted((IAM_ROOT / folder).rglob("*.py"))


@pytest.mark.parametrize(
    "path", sorted(IAM_ROOT.rglob("*.py")), ids=lambda path: path.name
)
def test_iam_does_not_import_web_frameworks(path: Path) -> None:
    roots = {module.split(".")[0] for module in imported_modules(path)}
    assert not roots & FRAMEWORKS, f"{path} імпортує фреймворк"


@pytest.mark.parametrize(
    "path", python_files("domain"), ids=lambda path: path.name
)
def test_domain_uses_only_stdlib_and_itself(path: Path) -> None:
    for module in imported_modules(path):
        allowed = (
            module.split(".")[0] in sys.stdlib_module_names
            or module.startswith("src.iam.domain")
            or module == "__future__"
        )
        assert allowed, f"{path.name}: заборонений імпорт {module}"


@pytest.mark.parametrize(
    "path", python_files("application"), ids=lambda path: path.name
)
def test_application_does_not_depend_on_infrastructure(path: Path) -> None:
    for module in imported_modules(path):
        assert not module.startswith("src.iam.infrastructure"), (
            f"{path.name}: сценарій має залежати від порту, а не від "
            f"адаптера {module}"
        )


# File was created by Claude (AI-assisted); review by a team member pending.
