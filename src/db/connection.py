"""Адреса бази з оточення та пул з'єднань.

Пул тримає кілька відкритих з'єднань і видає їх запитам по черзі:
відкривати нове з'єднання на кожен HTTP-запит повільно. Маршрути
FastAPI зараз синхронні (виконуються в пулі потоків), тому пул теж
синхронний; для WebSocket-модуля згодом знадобиться
``AsyncConnectionPool`` з того ж пакета.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL_ENV = "DATABASE_URL"

# .env лежить у корені репозиторію: src/db/connection.py → ../../.env
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_env_file(path: Path = ENV_FILE) -> bool:
    """Завантажує змінні з файла ``.env`` в оточення процесу.

    Уже задані змінні НЕ перезаписуються: значення з CI чи з
    терміналу важливіші за файл. Так ``.env`` працює однаково на
    macOS, Linux і Windows, і його не треба вручну «source»-ити.
    Повертає ``True``, якщо з файла задано хоча б одну змінну.
    """
    return load_dotenv(path, override=False)


def database_url() -> str | None:
    """Повертає адресу бази з ``DATABASE_URL`` або ``None``.

    Формат: ``postgresql://користувач:пароль@сервер:порт/база``.
    Порожнє значення вважається відсутнім.
    """
    value = os.environ.get(DATABASE_URL_ENV, "").strip()
    return value or None


def create_pool(
    url: str,
    *,
    min_size: int = 1,
    max_size: int = 10,
    open_immediately: bool = True,
) -> ConnectionPool:
    """Створює пул з'єднань; за замовчуванням чекає на готовність бази.

    Рядки результатів повертаються словниками (``row["email"]``), а
    не кортежами: так адаптери не залежать від порядку колонок.
    ``open_immediately=False`` дає змогу створити застосунок без
    підключення до БД під час імпорту; пул відкривається в lifespan.

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
    if open_immediately:
        pool.open(wait=True, timeout=10)
    return pool


# File was created by Claude. Reviewed by Kozynska Anastasia
