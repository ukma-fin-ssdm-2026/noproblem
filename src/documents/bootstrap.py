"""Збирання модуля «Документи» з адаптерів.

``build_documents`` повертає сервіс разом зі сховищами: сховища
потрібні ще й пошуку (``SearchService`` читає ті самі документи).
Без пулу з'єднань сховища працюють у пам'яті, з пулом — у PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from src.documents.adapters import (
    InMemoryDocumentRepository,
    InMemoryDocumentStore,
    InMemoryParagraphRepository,
)
from src.documents.ports import DocumentRepository, ParagraphRepository
from src.documents.postgres import (
    PostgresDocumentRepository,
    PostgresParagraphRepository,
)
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
    access: AccessService,
    *,
    clock: Clock | None = None,
    pool: ConnectionPool | None = None,
) -> DocumentsModule:
    """Створює модуль документів.

    Args:
        access: Сервіс доступу IAM (перевірка прав, I-11).
        clock: Годинник; за замовчуванням системний (UTC).
        pool: Пул PostgreSQL; якщо задано, документи зберігаються в
            базі, інакше — у пам'яті.
    """
    documents: DocumentRepository
    paragraphs: ParagraphRepository
    if pool is None:
        store = InMemoryDocumentStore()
        documents = InMemoryDocumentRepository(store)
        paragraphs = InMemoryParagraphRepository(store)
    else:
        documents = PostgresDocumentRepository(pool)
        paragraphs = PostgresParagraphRepository(pool)
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
