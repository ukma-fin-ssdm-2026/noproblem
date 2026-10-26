"""Сутності модуля «Документи»: документ, абзац і допоміжні типи.

Поки що це лише дані без поведінки: правила (довжина назви, «Без
назви», перенумерація абзаців) переїдуть сюди з ``src/api/main.py``
під час винесення модуля. Моделі не залежать ні від FastAPI, ні від
бази даних, тож однаково працюють зі сховищем у пам'яті й з
PostgreSQL (ADR-002).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class AccessMode(str, Enum):
    """Режим доступу до документа (FR-044)."""

    RESTRICTED = "restricted"  # лише явно запрошені (за замовчуванням)
    LINK = "link"  # будь-який автентифікований користувач із посиланням


@dataclass(frozen=True)
class Document:
    """Документ (сутність Document у data-model.md).

    ``deleted_at`` не ``None`` означає, що документ лежить у кошику
    (FR-019); через 30 днів його видаляють остаточно (FR-023).
    """

    id: int
    title: str
    access_mode: AccessMode
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @property
    def is_trashed(self) -> bool:
        """Чи лежить документ у кошику."""
        return self.deleted_at is not None


@dataclass(frozen=True)
class Paragraph:
    """Абзац документа (окрема таблиця Paragraph, ADR-001, ADR-002).

    Позиції абзаців одного документа завжди йдуть підряд від нуля:
    0, 1, 2, … Сховище підтримує це правило після кожної зміни.
    """

    id: int
    document_id: int
    position: int
    content: str


@dataclass(frozen=True)
class CreateOutcome:
    """Результат створення документа з ключем ідемпотентності (FR-013).

    ``created`` — ``False``, якщо документ із цим ключем уже існував і
    сховище повернуло його замість нового. ``requested_title`` — назва
    з *першого* запиту з цим ключем: сервіс порівнює її з поточною і
    повертає 409, якщо ключ повторили з іншою назвою.
    """

    document: Document
    created: bool
    requested_title: str


@dataclass(frozen=True)
class Page(Generic[T]):
    """Одна сторінка списку та загальна кількість елементів."""

    items: list[T]
    total: int


# File was created by Claude. Reviewed by Kozynska Anastasia
