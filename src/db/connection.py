"""Адреса бази з оточення та пул з'єднань.

Пул тримає кілька відкритих з'єднань і видає їх запитам по черзі:
відкривати нове з'єднання на кожен HTTP-запит повільно. Маршрути
FastAPI зараз синхронні (виконуються в пулі потоків), тому пул теж
синхронний; для WebSocket-модуля згодом знадобиться
``AsyncConnectionPool`` з того ж пакета.
"""

from __future__ import annotations

import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL_ENV = "DATABASE_URL"


def database_url() -> str | None:
    """Повертає адресу бази з ``DATABASE_URL`` або ``None``.

    Формат: ``postgresql://користувач:пароль@сервер:порт/база``.
    Порожнє значення вважається відсутнім.
    """
    value = os.environ.get(DATABASE_URL_ENV, "").strip()
    return value or None


def create_pool(
    url: str, *, min_size: int = 1, max_size: int = 10
) -> ConnectionPool:
    """Відкриває пул з'єднань і чекає, доки база відповість.

    Рядки результатів повертаються словниками (``row["email"]``), а
    не кортежами: так адаптери не залежать від порядку колонок.

    Raises:
        psycopg_pool.PoolTimeout: База не відповіла за 10 секунд.
    """
    pool = ConnectionPool(
        url,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    pool.open(wait=True, timeout=10)
    return pool


# File was created by Claude. Reviewed by Kozynska Anastasia
