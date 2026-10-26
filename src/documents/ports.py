"""Порти: інтерфейси, через які модуль «Документи» працює зі сховищем.

Порт описує, *що* потрібно сервісу, а не *як* це зроблено. Буде дві
реалізації кожного порту: у пам'яті (для тестів і запуску без БД) та
PostgreSQL (ADR-002, інтерфейс I-14). Сервіс документів, пошук
(I-07, I-16) і планувальник (I-18) знають лише ці протоколи.

Перевірку прав порти НЕ роблять: її виконує IAM до звернення до
сховища (I-11). Тому методи списків приймають уже відфільтровані
``document_ids`` — множину документів, доступних користувачеві.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.documents.models import (
    CreateOutcome,
    Document,
    Page,
    Paragraph,
)


class DocumentRepository(Protocol):
    """Сховище документів, кошика й ключів ідемпотентності."""

    def create(
        self,
        owner_id: UUID,
        idempotency_key: str,
        title: str,
        now: datetime,
    ) -> CreateOutcome:
        """Атомарно створює документ або повертає вже створений.

        Ключ ідемпотентності діє в межах користувача (``owner_id``).
        Якщо пара «користувач + ключ» уже траплялася, новий документ
        не створюється: повертається попередній і ``created=False``.
        Створення документа і запис ключа — одна операція: у
        PostgreSQL це одна транзакція, тож обрив з'єднання не лишає
        ні документа без ключа, ні ключа без документа (FR-013).

        Новий документ має режим «Обмежений» (FR-009). Роль Owner
        надає IAM окремим викликом; якщо він не відбувся, повтор із
        тим самим ключем поверне той самий документ, і сервіс надасть
        роль повторно.
        """
        ...

    def get(self, document_id: int) -> Document | None:
        """Документ за id — активний або з кошика; ``None``, якщо немає."""
        ...

    def list_active(
        self, document_ids: Collection[int], limit: int, offset: int
    ) -> Page[Document]:
        """Сторінка активних документів серед ``document_ids``.

        Документи з кошика не включаються; порядок — за зростанням id.
        """
        ...

    def list_trashed(
        self, document_ids: Collection[int], limit: int, offset: int
    ) -> Page[Document]:
        """Сторінка документів у кошику серед ``document_ids``.

        Порядок — від останнього видаленого до найдавнішого (FR-018).
        """
        ...

    def update(
        self, document_id: int, change: Callable[[Document], Document]
    ) -> Document | None:
        """Атомарно застосовує ``change`` до актуального стану документа.

        Один метод для перейменування (FR-014), переміщення в кошик
        (FR-019), відновлення (FR-020) і оновлення ``updated_at``.
        Сховище гарантує, що між читанням і записом документ ніхто не
        змінить (у PostgreSQL — ``SELECT ... FOR UPDATE``). Повертає
        новий стан або ``None``, якщо документа немає.
        """
        ...

    def purge_trashed_before(self, cutoff: datetime) -> list[int]:
        """Остаточно видаляє документи, переміщені в кошик до ``cutoff``.

        Разом із документом видаляються його абзаци й ключі
        ідемпотентності. Повертає id видалених документів, щоб
        викликач міг прибрати пов'язані записи в інших модулях
        (доступи в IAM). Планувальник передає ``now - 30 днів``
        (FR-023, I-18).
        """
        ...


class ParagraphRepository(Protocol):
    """Сховище абзаців документа (таблиця Paragraph, ADR-001)."""

    def list_for_document(self, document_id: int) -> list[Paragraph]:
        """Усі абзаци документа в порядку позицій."""
        ...

    def get(self, document_id: int, paragraph_id: int) -> Paragraph | None:
        """Абзац цього документа або ``None``."""
        ...

    def insert(
        self, document_id: int, position: int | None, content: str
    ) -> Paragraph:
        """Вставляє абзац і зсуває наступні; ``None`` — у кінець.

        Raises:
            ParagraphPositionError: ``position`` більша за кількість
                абзаців.
        """
        ...

    def update(
        self,
        document_id: int,
        paragraph_id: int,
        content: str | None,
        position: int | None,
    ) -> Paragraph | None:
        """Змінює текст і/або позицію абзацу; ``None`` лишає як було.

        Після переміщення позиції знову йдуть підряд від нуля.
        Повертає новий стан або ``None``, якщо абзацу немає.

        Raises:
            ParagraphPositionError: Нова позиція поза документом.
        """
        ...

    def delete(self, document_id: int, paragraph_id: int) -> bool:
        """Видаляє абзац і зсуває наступні; ``False``, якщо його не було."""
        ...


# File was created by Claude. Reviewed by Kozynska Anastasia
