"""PostgreSQL repositories for calendar events and participants."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.calendar_events.models import Event
from src.calendar_events.ports import EventRepository, ParticipantRepository

_COLUMNS = (
    "id, creator_id, title, start_at, end_at, "
    "document_id, created_at, updated_at"
)


def _to_event(row: dict) -> Event:
    return Event(
        id=row["id"],
        creator_id=row["creator_id"],
        title=row["title"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        document_id=row["document_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresCalendarRepository(EventRepository, ParticipantRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(self, event: Event) -> Event:
        query = f"""
            INSERT INTO calendar_events
                (creator_id, title, start_at, end_at,
                 document_id, created_at, updated_at)
            VALUES (%(creator_id)s, %(title)s, %(start_at)s, %(end_at)s,
                    %(document_id)s, %(created_at)s, %(updated_at)s)
            RETURNING {_COLUMNS};
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    query,
                    {
                        "creator_id": event.creator_id,
                        "title": event.title,
                        "start_at": event.start_at,
                        "end_at": event.end_at,
                        "document_id": event.document_id,
                        "created_at": event.created_at,
                        "updated_at": event.updated_at,
                    },
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(
                        "Створену подію не повернула база даних."
                    )
                return _to_event(row)

    def get(self, event_id: int) -> Event | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"SELECT {_COLUMNS} FROM calendar_events WHERE id = %s;",
                    (event_id,),
                )
                row = cur.fetchone()
                return _to_event(row) if row else None

    def update(self, event: Event) -> Event:
        query = f"""
            UPDATE calendar_events
            SET title = %(title)s, start_at = %(start_at)s,
                end_at = %(end_at)s, document_id = %(document_id)s,
                updated_at = %(updated_at)s
            WHERE id = %(id)s
            RETURNING {_COLUMNS};
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    query,
                    {
                        "id": event.id,
                        "title": event.title,
                        "start_at": event.start_at,
                        "end_at": event.end_at,
                        "document_id": event.document_id,
                        "updated_at": event.updated_at,
                    },
                )
                row = cur.fetchone()
                if row is None:
                    raise LookupError(f"Подію {event.id} не знайдено.")
                return _to_event(row)

    def delete(self, event_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM calendar_events WHERE id = %s;", (event_id,)
            )

    def list_in_range(
        self, user_id: UUID, start: datetime, end: datetime
    ) -> list[Event]:
        query = f"""
            SELECT {_COLUMNS} FROM calendar_events e
            WHERE (
                e.creator_id = %(user_id)s
                OR EXISTS (
                    SELECT 1 FROM calendar_event_participants p
                    WHERE p.event_id = e.id AND p.user_id = %(user_id)s
                )
            )
            AND e.start_at < %(end)s AND e.end_at > %(start)s
            ORDER BY e.start_at, e.id;
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    query, {"user_id": user_id, "start": start, "end": end}
                )
                return [_to_event(row) for row in cur.fetchall()]

    def add(self, event_id: int, user_id: UUID) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO calendar_event_participants (event_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING;
                """,
                (event_id, user_id),
            )

    def remove(self, event_id: int, user_id: UUID) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                DELETE FROM calendar_event_participants
                WHERE event_id = %s AND user_id = %s;
                """,
                (event_id, user_id),
            )

    def list_for_event(self, event_id: int) -> list[UUID]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT user_id FROM calendar_event_participants
                WHERE event_id = %s
                ORDER BY user_id::text;
                """,
                (event_id,),
            ).fetchall()
            return [row["user_id"] for row in rows]
