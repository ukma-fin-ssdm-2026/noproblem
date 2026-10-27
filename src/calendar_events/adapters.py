"""In-memory repositories for calendar events and participants."""

from __future__ import annotations

from datetime import datetime
from threading import RLock
from uuid import UUID

from src.calendar_events.models import Event
from src.calendar_events.ports import EventRepository, ParticipantRepository


class InMemoryCalendarRepository(EventRepository, ParticipantRepository):
    """Stores events and their participant ids in process memory."""

    def __init__(self) -> None:
        self._events: dict[int, Event] = {}
        self._participants: dict[int, set[UUID]] = {}
        self._next_id = 1
        self._lock = RLock()

    def create(self, event: Event) -> Event:
        with self._lock:
            stored = event
            if event.id == 0:
                stored = Event(
                    id=self._next_id,
                    creator_id=event.creator_id,
                    title=event.title,
                    start_at=event.start_at,
                    end_at=event.end_at,
                    document_id=event.document_id,
                    created_at=event.created_at,
                    updated_at=event.updated_at,
                )
            elif event.id in self._events:
                raise ValueError(f"Подію {event.id} уже існує.")
            self._next_id = max(self._next_id, stored.id + 1)
            self._events[stored.id] = stored
            return stored

    def get(self, event_id: int) -> Event | None:
        with self._lock:
            return self._events.get(event_id)

    def update(self, event: Event) -> Event:
        with self._lock:
            if event.id not in self._events:
                raise LookupError(f"Подію {event.id} не знайдено.")
            self._events[event.id] = event
            return event

    def delete(self, event_id: int) -> None:
        with self._lock:
            self._events.pop(event_id, None)
            self._participants.pop(event_id, None)

    def list_in_range(
        self, user_id: UUID, start: datetime, end: datetime
    ) -> list[Event]:
        with self._lock:
            matching = [
                event
                for event in self._events.values()
                if (
                    event.creator_id == user_id
                    or user_id in self._participants.get(event.id, set())
                )
                and event.start_at < end
                and event.end_at > start
            ]
        return sorted(matching, key=lambda event: (event.start_at, event.id))

    def add(self, event_id: int, user_id: UUID) -> None:
        with self._lock:
            self._participants.setdefault(event_id, set()).add(user_id)

    def remove(self, event_id: int, user_id: UUID) -> None:
        with self._lock:
            self._participants.setdefault(event_id, set()).discard(user_id)

    def list_for_event(self, event_id: int) -> list[UUID]:
        with self._lock:
            participants = self._participants.get(event_id, set())
            return sorted(participants, key=str)
