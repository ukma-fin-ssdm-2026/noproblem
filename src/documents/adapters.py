"""Сховища документів і абзаців у пам'яті процесу.

Реалізують порти ``DocumentRepository`` і ``ParagraphRepository``.
Дані зникають після перезапуску; це версія для тестів і для запуску
без бази. PostgreSQL-версія тих самих портів з'явиться в
``postgres.py``.

Обидва сховища працюють поверх одного ``InMemoryDocumentStore``, як
дві таблиці однієї бази: так остаточне видалення документа прибирає й
його абзаци (у PostgreSQL це робить ON DELETE CASCADE).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from src.documents.errors import InsertPositionError, MovePositionError
from src.documents.models import (
    AccessMode,
    CreateOutcome,
    Document,
    Page,
    Paragraph,
)


@dataclass
class InMemoryDocumentStore:
    """Спільний стан обох сховищ; змінюється лише під ``lock``."""

    lock: threading.RLock = field(default_factory=threading.RLock)
    documents: dict[int, Document] = field(default_factory=dict)
    # Абзаци кожного документа впорядковані за позицією 0, 1, 2, …
    paragraphs: dict[int, list[Paragraph]] = field(default_factory=dict)
    # (користувач, ключ) → (назва з першого запиту, id документа)
    idempotency: dict[tuple[UUID, str], tuple[str, int]] = field(
        default_factory=dict
    )
    next_document_id: int = 1
    next_paragraph_id: int = 1


class InMemoryDocumentRepository:
    """Реалізує ``DocumentRepository``."""

    def __init__(self, store: InMemoryDocumentStore) -> None:
        self._store = store

    def create(
        self,
        owner_id: UUID,
        idempotency_key: str,
        title: str,
        now: datetime,
    ) -> CreateOutcome:
        store = self._store
        with store.lock:
            record = store.idempotency.get((owner_id, idempotency_key))
            if record is not None:
                requested_title, document_id = record
                return CreateOutcome(
                    document=store.documents[document_id],
                    created=False,
                    requested_title=requested_title,
                )
            document = Document(
                id=store.next_document_id,
                title=title,
                access_mode=AccessMode.RESTRICTED,
                created_at=now,
                updated_at=now,
            )
            store.next_document_id += 1
            store.documents[document.id] = document
            store.paragraphs[document.id] = []
            store.idempotency[(owner_id, idempotency_key)] = (
                title,
                document.id,
            )
            return CreateOutcome(
                document=document, created=True, requested_title=title
            )

    def get(self, document_id: int) -> Document | None:
        with self._store.lock:
            return self._store.documents.get(document_id)

    def list_active(
        self, document_ids: Collection[int], limit: int, offset: int
    ) -> Page[Document]:
        with self._store.lock:
            active = [
                document
                for document_id, document in sorted(
                    self._store.documents.items()
                )
                if document_id in document_ids and not document.is_trashed
            ]
        return Page(items=active[offset : offset + limit], total=len(active))

    def list_trashed(
        self, document_ids: Collection[int], limit: int, offset: int
    ) -> Page[Document]:
        with self._store.lock:
            trashed = [
                document
                for document_id, document in sorted(
                    self._store.documents.items()
                )
                if document_id in document_ids and document.is_trashed
            ]
        # Сортування стабільне: за однакового часу лишається порядок id.
        trashed.sort(key=_deleted_at, reverse=True)
        return Page(items=trashed[offset : offset + limit], total=len(trashed))

    def update(
        self, document_id: int, change: Callable[[Document], Document]
    ) -> Document | None:
        with self._store.lock:
            current = self._store.documents.get(document_id)
            if current is None:
                return None
            updated = change(current)  # виняток тут → нічого не записано
            if updated.id != current.id:
                raise ValueError("update не може змінювати id документа.")
            self._store.documents[document_id] = updated
            return updated

    def purge_trashed_before(self, cutoff: datetime) -> list[int]:
        store = self._store
        with store.lock:
            expired = sorted(
                document.id
                for document in store.documents.values()
                if document.deleted_at is not None
                and document.deleted_at <= cutoff
            )
            for document_id in expired:
                del store.documents[document_id]
                store.paragraphs.pop(document_id, None)
            expired_set = set(expired)
            for key, (_, document_id) in list(store.idempotency.items()):
                if document_id in expired_set:
                    del store.idempotency[key]
            return expired


class InMemoryParagraphRepository:
    """Реалізує ``ParagraphRepository``."""

    def __init__(self, store: InMemoryDocumentStore) -> None:
        self._store = store

    def list_for_document(self, document_id: int) -> list[Paragraph]:
        with self._store.lock:
            return list(self._store.paragraphs.get(document_id, []))

    def get(self, document_id: int, paragraph_id: int) -> Paragraph | None:
        with self._store.lock:
            return _find(
                self._store.paragraphs.get(document_id, []), paragraph_id
            )

    def insert(
        self, document_id: int, position: int | None, content: str
    ) -> Paragraph:
        store = self._store
        with store.lock:
            ordered = list(store.paragraphs.get(document_id, []))
            target = len(ordered) if position is None else position
            if target > len(ordered):
                raise InsertPositionError()
            paragraph = Paragraph(
                id=store.next_paragraph_id,
                document_id=document_id,
                position=target,
                content=content,
            )
            store.next_paragraph_id += 1
            ordered.insert(target, paragraph)
            store.paragraphs[document_id] = _renumbered(ordered)
            return store.paragraphs[document_id][target]

    def update(
        self,
        document_id: int,
        paragraph_id: int,
        content: str | None,
        position: int | None,
    ) -> Paragraph | None:
        store = self._store
        with store.lock:
            ordered = list(store.paragraphs.get(document_id, []))
            current = _find(ordered, paragraph_id)
            if current is None:
                return None
            target = current.position if position is None else position
            if target >= len(ordered):
                raise MovePositionError()
            ordered.pop(current.position)
            new_content = current.content if content is None else content
            ordered.insert(target, replace(current, content=new_content))
            store.paragraphs[document_id] = _renumbered(ordered)
            return store.paragraphs[document_id][target]

    def delete(self, document_id: int, paragraph_id: int) -> bool:
        store = self._store
        with store.lock:
            ordered = store.paragraphs.get(document_id, [])
            remaining = [p for p in ordered if p.id != paragraph_id]
            if len(remaining) == len(ordered):
                return False
            store.paragraphs[document_id] = _renumbered(remaining)
            return True


def _deleted_at(document: Document) -> datetime:
    # Викликається лише для документів з кошика, де deleted_at задано.
    return document.deleted_at or datetime.min


def _find(paragraphs: list[Paragraph], paragraph_id: int) -> Paragraph | None:
    return next((p for p in paragraphs if p.id == paragraph_id), None)


def _renumbered(paragraphs: list[Paragraph]) -> list[Paragraph]:
    """Позиції знову підряд від нуля в поточному порядку списку."""
    return [
        (
            paragraph
            if paragraph.position == index
            else replace(paragraph, position=index)
        )
        for index, paragraph in enumerate(paragraphs)
    ]


# File was created by Claude. Reviewed by Kozynska Anastasia
