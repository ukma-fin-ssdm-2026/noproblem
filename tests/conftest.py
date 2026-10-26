"""Спільні фікстури pytest."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import ConnectionPool

from src.db import create_pool, load_env_file
from src.db.migrate import apply_migrations
from src.iam import AccessService, AuthService, build_access, build_iam
from tests.fakes import FakeClock, FakePasswordHasher, RecordingEmailSender

VALID_EMAIL = "olena@example.com"
VALID_NAME = "Олена"
VALID_PASSWORD = "correct-horse"  # nosec B105 — тестові дані


@dataclass
class IamTestEnv:
    """Сервіси IAM разом із підробками, якими тест керує."""

    iam: AuthService
    access: AccessService
    clock: FakeClock
    hasher: FakePasswordHasher
    mail: RecordingEmailSender


@pytest.fixture
def env() -> IamTestEnv:
    clock = FakeClock()
    hasher = FakePasswordHasher()
    mail = RecordingEmailSender()
    iam = build_iam(clock=clock, password_hasher=hasher, email_sender=mail)
    return IamTestEnv(
        iam=iam,
        access=build_access(iam),
        clock=clock,
        hasher=hasher,
        mail=mail,
    )


#
# PostgreSQL. Тести працюють з ОКРЕМОЮ базою з TEST_DATABASE_URL (у
# docker-compose це notely_test), бо після кожного тесту всі таблиці
# очищаються. Робоча база з DATABASE_URL тестами не зачіпається.
# Без TEST_DATABASE_URL ці тести позначаються як skipped, а не падають.
#

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"

# Змінні з .env (локально) — щоб не задавати їх вручну в терміналі.
load_env_file()


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Адреса тестової бази з уже застосованими міграціями."""
    url = os.environ.get(TEST_DATABASE_URL_ENV, "").strip()
    if not url:
        pytest.skip(
            f"{TEST_DATABASE_URL_ENV} не задано: тести PostgreSQL пропущено."
        )
    database_name = conninfo_to_dict(url).get("dbname") or ""
    if not str(database_name).endswith("_test"):
        # Запобіжник: тести очищають усі таблиці, тож ніколи не
        # запускаємо їх на базі, яка не позначена як тестова.
        pytest.fail(
            f"{TEST_DATABASE_URL_ENV} має вказувати на базу з назвою на "
            f"«_test», а не на «{database_name}»: тести стирають дані."
        )
    with psycopg.connect(url, autocommit=True) as conn:
        apply_migrations(conn)
    return url


@pytest.fixture(scope="session")
def _session_pool(postgres_url: str) -> Iterator[ConnectionPool]:
    pool = create_pool(postgres_url, max_size=4)
    yield pool
    pool.close()


@pytest.fixture
def pg_pool(_session_pool: ConnectionPool) -> Iterator[ConnectionPool]:
    """Пул з'єднань до чистої бази: після тесту всі таблиці очищаються.

    Цей пул передають у PostgreSQL-адаптери, наприклад
    ``PostgresUserRepository(pg_pool)``.
    """
    yield _session_pool
    with _session_pool.connection() as conn:
        _truncate_all_tables(conn)


def _truncate_all_tables(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename <> 'schema_migrations'"
    ).fetchall()
    tables = [row["tablename"] for row in rows]
    if tables:
        conn.execute(
            sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(", ").join(sql.Identifier(name) for name in tables)
            )
        )


# File was created by Claude. Reviewed by Kozynska Anastasia
# PostgreSQL fixtures added by Claude. Reviewed by Kozynska Anastasia
