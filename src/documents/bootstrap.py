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
    InMemoryVersionRepository,
)
from src.documents.ports import (
    DocumentEvents,
    DocumentRepository,
    ParagraphLocks,
    ParagraphRepository,
    VersionRepository,
)
from src.documents.postgres import (
    PostgresDocumentRepository,
    PostgresParagraphRepository,
    PostgresVersionRepository,
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
    versions: VersionRepository


def build_documents(
    access: AccessService,
    *,
    clock: Clock | None = None,
    pool: ConnectionPool | None = None,
    locks: ParagraphLocks | None = None,
    events: DocumentEvents | None = None,
) -> DocumentsModule:
    """Створює модуль документів.

    Args:
        access: Сервіс доступу IAM (перевірка прав, I-11).
        clock: Годинник; за замовчуванням системний (UTC).
        pool: Пул PostgreSQL; якщо задано, документи зберігаються в
            базі, інакше — у пам'яті.
        events: Отримувач подій про зміни документів; необов'язковий.
    """
    documents: DocumentRepository
    paragraphs: ParagraphRepository
    versions: VersionRepository
    if pool is None:
        store = InMemoryDocumentStore()
        documents = InMemoryDocumentRepository(store)
        paragraphs = InMemoryParagraphRepository(store)
        versions = InMemoryVersionRepository(store)
    else:
        documents = PostgresDocumentRepository(pool)
        paragraphs = PostgresParagraphRepository(pool)
        versions = PostgresVersionRepository(pool)
    service = DocumentService(
        documents=documents,
        paragraphs=paragraphs,
        versions=versions,
        access=access,
        clock=clock or SystemClock(),
        locks=locks,
        events=events,
    )
    return DocumentsModule(
        service=service,
        documents=documents,
        paragraphs=paragraphs,
        versions=versions,
    )


# File was created by Claude. Reviewed by Kozynska Anastasia
