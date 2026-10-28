from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.calendar_events.adapters import InMemoryCalendarRepository
from src.calendar_events.models import Event


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
