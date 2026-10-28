"""Тести підключення до PostgreSQL і міграцій (src/db).

Перша група працює без бази. Друга просить фікстуру ``postgres_url``
або ``pg_pool`` і без ``TEST_DATABASE_URL`` позначається як skipped.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from src.db import DATABASE_URL_ENV, database_url, load_env_file
from src.db import migrate
from src.db.migrate import apply_migrations, migration_files

#
# Без бази
#


def test_database_url_comes_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "postgresql://user:secret@db:5432/notely"
    monkeypatch.setenv(DATABASE_URL_ENV, f"  {url}  ")
    assert database_url() == url


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_database_url_is_none(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    else:
        monkeypatch.setenv(DATABASE_URL_ENV, value)
    assert database_url() is None


def test_project_migrations_are_numbered_in_order() -> None:
    names = [path.stem for path in migration_files()]
    assert names[:4] == [
        "001_iam",
        "002_documents",
        "003_access_requests",
        "004_calendar_events",
    ]


@pytest.mark.parametrize(
    "bad_name", ["1_iam.sql", "001-iam.sql", "001_IAM.sql", "001_.sql"]
)
def test_badly_named_migration_is_rejected(
    tmp_path: Path, bad_name: str
) -> None:
    (tmp_path / bad_name).write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(ValueError, match="NNN_назва.sql"):
        migration_files(tmp_path)


def test_duplicate_migration_number_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "003_calendar.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "003_search.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(ValueError, match="003"):
        migration_files(tmp_path)


def test_env_file_fills_missing_variables_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NOTELY_NEW_VAR=from-file\nNOTELY_SET_VAR=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NOTELY_NEW_VAR", raising=False)
    monkeypatch.setenv("NOTELY_SET_VAR", "from-terminal")
    try:
        assert load_env_file(env_file) is True
        assert os.environ["NOTELY_NEW_VAR"] == "from-file"
        # Значення з терміналу чи CI важливіше за файл.
        assert os.environ["NOTELY_SET_VAR"] == "from-terminal"
    finally:
        os.environ.pop("NOTELY_NEW_VAR", None)


def test_cli_without_database_url_fails_with_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    # Інакше main() підвантажив би DATABASE_URL з локального .env.
    monkeypatch.setattr(migrate, "load_env_file", lambda: False)
    assert migrate.main() == 1
    assert DATABASE_URL_ENV in capsys.readouterr().err


#
# З базою
#


def test_migrations_create_all_tables(pg_pool: ConnectionPool) -> None:
    with pg_pool.connection() as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    tables = {row["tablename"] for row in rows}
    assert {
        "schema_migrations",
        "users",
        "sessions",
        "unlock_tokens",
        "document_access",
        "documents",
        "paragraphs",
        "idempotency_keys",
        "access_requests",
        "calendar_events",
        "calendar_event_participants",
    } <= tables


def test_applying_twice_changes_nothing(postgres_url: str) -> None:
    with psycopg.connect(postgres_url, autocommit=True) as conn:
        assert apply_migrations(conn) == []


def test_failed_migration_leaves_no_trace(
    postgres_url: str, tmp_path: Path
) -> None:
    (tmp_path / "001_broken.sql").write_text(
        "CREATE TABLE must_not_exist (id INTEGER); SELECT 1 / 0;",
        encoding="utf-8",
    )
    with psycopg.connect(postgres_url, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.DivisionByZero):
            apply_migrations(conn, tmp_path)
        table = conn.execute("SELECT to_regclass('must_not_exist')").fetchone()
        recorded = conn.execute(
            "SELECT count(*) FROM schema_migrations "
            "WHERE version = '001_broken'"
        ).fetchone()
    assert table == (None,)
    assert recorded == (0,)


def test_cli_reports_up_to_date_schema(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    postgres_url: str,
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_url)
    assert migrate.main() == 0
    assert "актуальна" in capsys.readouterr().out


def test_pool_returns_rows_as_dicts(pg_pool: ConnectionPool) -> None:
    with pg_pool.connection() as conn:
        row = conn.execute("SELECT 1 AS answer").fetchone()
    assert row == {"answer": 1}


def test_paragraph_positions_can_be_swapped_but_not_duplicated(
    pg_pool: ConnectionPool,
) -> None:
    """Схема дозволяє перенумерацію в транзакції, але не дублікати."""
    with pg_pool.connection() as conn:
        document_id = conn.execute(
            "INSERT INTO documents (title, created_at, updated_at) "
            "VALUES ('Тест', now(), now()) RETURNING id"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO paragraphs (document_id, position, content) "
            "VALUES (%s, 0, 'a'), (%s, 1, 'b')",
            (document_id, document_id),
        )
        conn.commit()
        conn.execute(
            "UPDATE paragraphs SET position = 1 - position "
            "WHERE document_id = %s",
            (document_id,),
        )
        conn.commit()
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                "INSERT INTO paragraphs (document_id, position, content) "
                "VALUES (%s, 0, 'dup')",
                (document_id,),
            )
            conn.commit()
        conn.rollback()


# File was created by Claude. Reviewed by Kozynska Anastasia
