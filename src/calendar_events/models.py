from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Event:
    id: int
    creator_id: UUID
    title: str
    start_at: datetime
    end_at: datetime
    document_id: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Participant:
    event_id: int
    user_id: UUID


# File was created by Copilot and reviewed by Olha Marushchenko
