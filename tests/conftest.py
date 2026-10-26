"""Спільні фікстури pytest."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import psycopg
import pytest
from psycopg import sql
from psycopg_pool import ConnectionPool

from src.db import create_pool, database_url
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
# PostgreSQL. Тести, що просять ці фікстури, виконуються лише тоді, коли
# задано DATABASE_URL (локально — після «docker compose up -d», у CI —
# завжди). Без бази вони позначаються як skipped, а не падають.
#


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Адреса тестової бази з уже застосованими міграціями."""
    url = database_url()
    if url is None:
        pytest.skip("DATABASE_URL не задано: тести PostgreSQL пропущено.")
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
