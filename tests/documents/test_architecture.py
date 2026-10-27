"""Архітектурні тести модуля «Документи» (як ``tests/iam``).

Правила:
1. Жоден файл ``src/documents`` не імпортує веб-фреймворки чи ORM:
   HTTP живе в ``src/api/documents.py``.
2. ``service.py`` і ``ports.py`` не імпортують адаптери: сервіс
   залежить від інтерфейсів, тож PostgreSQL-сховище підключається без
   змін у сервісі.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.iam.test_architecture import FRAMEWORKS, imported_modules

DOCUMENTS_ROOT = Path(__file__).resolve().parents[2] / "src" / "documents"
ADAPTERS = {"src.documents.adapters", "src.documents.postgres"}


@pytest.mark.parametrize(
    "path", sorted(DOCUMENTS_ROOT.glob("*.py")), ids=lambda path: path.name
)
def test_documents_do_not_import_web_frameworks(path: Path) -> None:
    roots = {module.split(".")[0] for module in imported_modules(path)}
    assert not roots & FRAMEWORKS, f"{path.name} імпортує фреймворк"


@pytest.mark.parametrize("name", ["service.py", "ports.py"])
def test_service_depends_on_ports_not_adapters(name: str) -> None:
    modules = imported_modules(DOCUMENTS_ROOT / name)
    assert not modules & ADAPTERS, f"{name} імпортує адаптер"


# File was created by Claude. Reviewed by Kozynska Anastasia
