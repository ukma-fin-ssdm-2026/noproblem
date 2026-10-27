"""Збирання модуля «Документи» з адаптерів.

``build_documents`` повертає сервіс разом зі сховищами: сховища
потрібні ще й пошуку (``SearchService`` читає ті самі документи).
Поки що сховища — у пам'яті; PostgreSQL-версія підключатиметься тут
же, коли задано пул з'єднань.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.documents.adapters import (
    InMemoryDocumentRepository,
    InMemoryDocumentStore,
    InMemoryParagraphRepository,
)
from src.documents.ports import DocumentRepository, ParagraphRepository
from src.documents.service import DocumentService
from src.iam import AccessService
from src.iam.adapters import SystemClock
from src.iam.ports import Clock


@dataclass(frozen=True)
class DocumentsModule:
    """Готовий до роботи модуль: сервіс і його сховища."""

    service: DocumentService
    documents: DocumentRepository
    paragraphs: ParagraphRepository


def build_documents(
    access: AccessService, *, clock: Clock | None = None
) -> DocumentsModule:
    """Створює модуль документів зі сховищами в пам'яті.

    Args:
        access: Сервіс доступу IAM (перевірка прав, I-11).
        clock: Годинник; за замовчуванням системний (UTC).
    """
    store = InMemoryDocumentStore()
    documents = InMemoryDocumentRepository(store)
    paragraphs = InMemoryParagraphRepository(store)
    service = DocumentService(
        documents=documents,
        paragraphs=paragraphs,
        access=access,
        clock=clock or SystemClock(),
    )
    return DocumentsModule(
        service=service, documents=documents, paragraphs=paragraphs
    )


# File was created by Claude. Reviewed by Kozynska Anastasia
