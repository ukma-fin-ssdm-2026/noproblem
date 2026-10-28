"""Перевіряє вибір PostgreSQL-сховищ через ``DATABASE_URL``."""

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


def test_database_url_uses_postgres_for_calendar(
    monkeypatch: pytest.MonkeyPatch,
    postgres_url: str,
    calendar_pg_pool: ConnectionPool,
) -> None:
    email = f"calendar-pg-{uuid4()}@example.com"
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    app = create_app()

    with TestClient(app) as client:
        owner = sign_up(client, email, "Calendar owner")
        response = client.post(
            "/api/v1/calendar/events",
            headers=owner,
            json={
                "title": "PostgreSQL planning",
                "start_at": "2026-10-28T10:00:00+00:00",
                "end_at": "2026-10-28T11:00:00+00:00",
            },
        )
        assert response.status_code == 201
        event_id = response.json()["id"]

        with app.state.database_pool.connection() as conn:
            event = conn.execute(
                "SELECT id, title FROM calendar_events WHERE id = %s",
                (event_id,),
            ).fetchone()

    assert event == {"id": event_id, "title": "PostgreSQL planning"}


def test_database_url_uses_postgres_for_documents(
    monkeypatch: pytest.MonkeyPatch,
    postgres_url: str,
    pg_pool: ConnectionPool,
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    app = create_app()

    with TestClient(app) as client:
        owner = sign_up(client, f"docs-pg-{uuid4()}@example.com", "Автор")
        document_id = create_document(client, owner, "Документ у базі")
        response = client.post(
            f"/api/v1/documents/{document_id}/paragraphs",
            headers=owner,
            json={"content": "Перший абзац"},
        )
        assert response.status_code == 201

        with app.state.database_pool.connection() as conn:
            document = conn.execute(
                "SELECT title FROM documents WHERE id = %s",
                (document_id,),
            ).fetchone()
            paragraph = conn.execute(
                "SELECT content FROM paragraphs WHERE document_id = %s",
                (document_id,),
            ).fetchone()

    assert document == {"title": "Документ у базі"}
    assert paragraph == {"content": "Перший абзац"}


# File was created by Claude. Reviewed and mdified by Kozynska Anastasia
