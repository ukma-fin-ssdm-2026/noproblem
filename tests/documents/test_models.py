"""Узгодженість моделей модуля «Документи» зі схемою бази.

Значення, які дозволяє Python, мають дозволятися й обмеженням CHECK у
SQL-міграціях. Інакше новий режим доступу пройде всі тести в пам'яті,
а PostgreSQL відхилятиме записи з ним.
"""

from __future__ import annotations

import re

from src.db.migrate import migration_files
from src.documents.models import AccessMode


def allowed_by_check(column: str) -> set[str]:
    """Значення з останнього ``CHECK (column IN (...))`` у міграціях.

    Береться останнє входження: якщо пізніша міграція змінить
    обмеження, тест перевірятиме вже його.
    """
    schema = "\n".join(
        path.read_text(encoding="utf-8") for path in migration_files()
    )
    matches = re.findall(rf"{column} IN \(([^)]*)\)", schema)
    assert matches, f"CHECK для {column} у міграціях не знайдено"
    return set(re.findall(r"'([^']*)'", matches[-1]))


def test_access_modes_match_database_check() -> None:
    expected = allowed_by_check("access_mode")
    assert {mode.value for mode in AccessMode} == expected


# File was created by Claude. Reviewed by Kozynska Anastasia
