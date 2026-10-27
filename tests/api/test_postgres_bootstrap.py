"""Перевіряє вибір IAM PostgreSQL-сховищ через ``DATABASE_URL``."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from src.api.main import create_app
from tests.api.helpers import create_document, sign_up


def test_database_url_uses_postgres_for_iam(
    monkeypatch: pytest.MonkeyPatch,
    postgres_url: str,
    pg_pool: ConnectionPool,
) -> None:
    email = f"pg-{uuid4()}@example.com"
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    app = create_app()

    with TestClient(app) as client:
        owner = sign_up(client, email, "Власник")
        document_id = create_document(client, owner, "IAM PostgreSQL")
        with app.state.database_pool.connection() as conn:
            user = conn.execute(
                "SELECT id FROM users WHERE email = %s",
                (email,),
            ).fetchone()
            assert user is not None
            session_count = conn.execute(
                "SELECT count(*) AS count FROM sessions WHERE user_id = %s",
                (user["id"],),
            ).fetchone()["count"]
            access = conn.execute(
                """
                SELECT role FROM document_access
                WHERE document_id = %s AND user_id = %s
                """,
                (document_id, user["id"]),
            ).fetchone()

    assert session_count == 1
    assert access == {"role": "owner"}
