"""Застосування SQL-міграцій з папки ``migrations/``.

Міграція — файл ``NNN_назва.sql``, що змінює схему бази. Файли
застосовуються по черзі за номером, кожен рівно один раз: список
застосованих зберігається в таблиці ``schema_migrations``. Уже
застосований файл не редагують — для змін пишуть новий.

Запуск вручну: ``python -m src.db.migrate`` (потрібен ``DATABASE_URL``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg
from psycopg.rows import tuple_row

from src.db.connection import DATABASE_URL_ENV, database_url

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME_PATTERN = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")

# Довільне фіксоване число для pg_advisory_lock: якщо два процеси
# застосунку стартують одночасно, міграції виконає лише один.
_MIGRATION_LOCK_ID = 20261026


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """Файли міграцій, відсортовані за номером.

    Raises:
        ValueError: Назва файла не відповідає формату ``NNN_назва.sql``
            або два файли мають однаковий номер.
    """
    files = sorted(directory.glob("*.sql"))
    numbers: set[str] = set()
    for path in files:
        if not _NAME_PATTERN.match(path.name):
            raise ValueError(
                f"Назва міграції {path.name!r} не відповідає формату "
                "NNN_назва.sql (малі латинські літери, цифри, _)."
            )
        number = path.name[:3]
        if number in numbers:
            raise ValueError(f"Дві міграції мають номер {number}.")
        numbers.add(number)
    return files


def apply_migrations(
    conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR
) -> list[str]:
    """Застосовує ще не застосовані міграції; повертає їхні назви.

    Кожна міграція виконується в окремій транзакції разом із записом
    у ``schema_migrations``: якщо SQL упав, не змінюється нічого, і
    наступний запуск спробує цю міграцію знову.
    """
    files = migration_files(directory)
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY,"
            " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_ID,))
    try:
        with conn.cursor(row_factory=tuple_row) as cursor:
            cursor.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cursor.fetchall()}
        newly_applied: list[str] = []
        for path in files:
            if path.stem in applied:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (path.stem,),
                )
            newly_applied.append(path.stem)
        return newly_applied
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_ID,))


def main() -> int:
    """Точка входу ``python -m src.db.migrate``; повертає код виходу."""
    url = database_url()
    if url is None:
        print(
            f"{DATABASE_URL_ENV} не задано: нема куди застосовувати "
            "міграції.",
            file=sys.stderr,
        )
        return 1
    with psycopg.connect(url, autocommit=True) as conn:
        applied = apply_migrations(conn, MIGRATIONS_DIR)
    if applied:
        print("Застосовано міграції: " + ", ".join(applied))
    else:
        print("Схема актуальна: нових міграцій немає.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


# File was created by Claude. Reviewed by Kozynska Anastasia
