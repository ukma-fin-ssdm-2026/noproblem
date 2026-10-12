"""Архітектурні тести: межа між бізнес-логікою та фреймворком.

Критерій 4 огляду коду Лаб 5 перевіряє, що бізнес-логіка не
переплетена з фреймворком. Домовленість, яку пам'ятають лише люди,
рано чи пізно порушать, тому тут її перевіряє CI. Тест розбирає
імпорти кожного файлу модулем ``ast``, не запускаючи код.

Правила:

1. Жоден файл ``src/iam`` не імпортує веб-фреймворки чи ORM.
2. ``models.py`` і ``errors.py`` (бізнес-правила) — лише стандартна
   бібліотека Python і імпорт одне одного.
3. ``service.py`` і ``ports.py`` не імпортують ``adapters.py``:
   сервіс залежить від інтерфейсів, а не від реалізацій.
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


@pytest.mark.parametrize(
    "path", sorted(IAM_ROOT.glob("*.py")), ids=lambda path: path.name
)
def test_iam_does_not_import_web_frameworks(path: Path) -> None:
    roots = {module.split(".")[0] for module in imported_modules(path)}
    assert not roots & FRAMEWORKS, f"{path.name} імпортує фреймворк"


@pytest.mark.parametrize("name", ["models.py", "errors.py"])
def test_business_rules_use_only_stdlib(name: str) -> None:
    for module in imported_modules(IAM_ROOT / name):
        allowed = (
            module.split(".")[0] in sys.stdlib_module_names
            or module in {"src.iam.models", "src.iam.errors"}
            or module == "__future__"
        )
        assert allowed, f"{name}: заборонений імпорт {module}"


@pytest.mark.parametrize("name", ["service.py", "access.py", "ports.py"])
def test_service_depends_on_ports_not_adapters(name: str) -> None:
    for module in imported_modules(IAM_ROOT / name):
        assert (
            module != "src.iam.adapters"
        ), f"{name}: сервіс має залежати від порту, а не від адаптера"


# File was created by Claude. Reviewed and modified by Kozynska Anastasia
