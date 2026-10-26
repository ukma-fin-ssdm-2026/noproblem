"""Тести моделей модуля «Документи» (src/documents).

Логіки тут поки небагато: вона переїде з ``src/api/main.py`` під час
винесення модуля. Тести фіксують поведінку моделі та її узгодженість зі
схемою бази.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from src.documents.models import AccessMode, Document

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def make_document(deleted_at: datetime | None = None) -> Document:
    return Document(
        id=1,
        title="Без назви",
        access_mode=AccessMode.RESTRICTED,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=deleted_at,
    )


def test_active_document_is_not_trashed() -> None:
    assert make_document().is_trashed is False


def test_document_with_deleted_at_is_trashed() -> None:
    assert make_document(deleted_at=NOW).is_trashed is True


def test_document_is_immutable() -> None:
    document = make_document()
    with pytest.raises(FrozenInstanceError):
        document.title = "Інша назва"  # type: ignore[misc]


def test_access_mode_values_match_database_check() -> None:
    # Ці рядки дозволяє CHECK у міграції 002_documents.sql.
    assert {mode.value for mode in AccessMode} == {"restricted", "link"}


# File was created by Claude. Reviewed by Kozynska Anastasia
