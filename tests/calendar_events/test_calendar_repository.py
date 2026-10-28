from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from psycopg_pool import ConnectionPool

from src.calendar_events.adapters import InMemoryCalendarRepository
from src.calendar_events.models import Event
from src.calendar_events.postgres import PostgresCalendarRepository


def test_postgres_calendar_repository_persists_events_and_participants(
    calendar_pg_pool: ConnectionPool,
) -> None:
    creator_id = UUID("78c4bb56-c41d-4d64-8f78-5db3632f3480")
    participant_id = UUID("6b63f5c2-48bc-47dd-a2d5-3d5cc9ae4a79")
    with calendar_pg_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO users (id, email, name, password_hash, created_at)
                VALUES (%s, %s, %s, 'test-hash', now())
                """,
                [
                    (creator_id, f"{creator_id}@example.com", "Creator"),
                    (
                        participant_id,
                        f"{participant_id}@example.com",
                        "Participant",
                    ),
                ],
            )

    repository = PostgresCalendarRepository(calendar_pg_pool)
    start = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
    event = Event(
        id=0,
        creator_id=creator_id,
        title="Planning",
        start_at=start,
        end_at=start + timedelta(hours=1),
        document_id=None,
        created_at=start,
        updated_at=start,
    )

    created = repository.create(event)
    assert created.id > 0
    assert repository.get(created.id) == created

    repository.add(created.id, participant_id)
    repository.add(created.id, participant_id)
    assert repository.list_for_event(created.id) == [participant_id]
    assert repository.list_in_range(
        participant_id,
        start + timedelta(minutes=30),
        start + timedelta(hours=2),
    ) == [created]

    updated = replace(created, title="Updated")
    assert repository.update(updated) == updated
    assert repository.get(created.id) == updated

    repository.delete(created.id)
    assert repository.get(created.id) is None
    assert repository.list_for_event(created.id) == []


def test_create_rejects_duplicate_explicit_event_id() -> None:
    repository = InMemoryCalendarRepository()
    now = datetime.now(timezone.utc)
    original = Event(
        id=7,
        creator_id=UUID("78c4bb56-c41d-4d64-8f78-5db3632f3480"),
        title="Planning",
        start_at=now,
        end_at=now + timedelta(hours=1),
        document_id=None,
        created_at=now,
        updated_at=now,
    )
    repository.create(original)

    with pytest.raises(ValueError, match="Подію 7 уже існує"):
        repository.create(replace(original, title="Replacement"))

    assert repository.get(7) == original
    assert repository.create(replace(original, id=0)).id == 8


# File was created by Copilot and reviewed by Olha Marushchenko
