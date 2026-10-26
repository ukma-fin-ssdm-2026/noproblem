"""Підключення до PostgreSQL і міграції схеми (ADR-002, I-14–I-17).

Модуль не містить логіки предметної області: лише читає адресу бази з
``DATABASE_URL``, відкриває пул з'єднань і застосовує SQL-міграції з
папки ``migrations/``. Адаптери модулів (``PostgresUserRepository``
тощо) отримують пул і виконують свої запити самі.

Без ``DATABASE_URL`` застосунок працює зі сховищами в пам'яті, як і
раніше: так не ламаються тести без бази й генерація OpenAPI.

Міграції — у ``src.db.migrate``. Їх свідомо не імпортуємо тут: інакше
``python -m src.db.migrate`` завантажував би модуль двічі й показував
RuntimeWarning.
"""

from src.db.connection import DATABASE_URL_ENV, create_pool, database_url

__all__ = ["DATABASE_URL_ENV", "create_pool", "database_url"]

# File was created by Claude. Reviewed by Kozynska Anastasia
