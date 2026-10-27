"""PostgreSQL-сховища документів і абзаців (ADR-002, інтерфейс I-14).

Реалізують ті самі порти, що й сховища в пам'яті (``adapters.py``), і
мають поводитися так само — це перевіряють спільні тести
``tests/documents/test_repositories.py``. Схема таблиць —
``src/db/migrations/002_documents.sql``.

Пул з'єднань має повертати рядки словниками (так налаштовує
``src.db.create_pool``). Значення в SQL передаються лише параметрами
``%s``, ніколи не вклеюються в текст запиту.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from src.documents.errors import InsertPositionError, MovePositionError
from src.documents.models import (
    AccessMode,
    CreateOutcome,
    Document,
    Page,
    Paragraph,
)


class PostgresDocumentRepository:
    """Реалізує ``DocumentRepository`` поверх таблиць documents і
    idempotency_keys."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(
        self,
        owner_id: UUID,
        idempotency_key: str,
        title: str,
        now: datetime,
    ) -> CreateOutcome:
        with self._pool.connection() as conn:
            existing = _find_by_key(conn, owner_id, idempotency_key)
            if existing is not None:
                return existing
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO documents (title, created_at, updated_at) "
                    "VALUES (%s, %s, %s) RETURNING id, title, access_mode, "
                    "created_at, updated_at, deleted_at",
                    (title, now, now),
                ).fetchone()
                claimed = conn.execute(
                    "INSERT INTO idempotency_keys "
                    "(user_id, key, requested_title, document_id) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (user_id, key) DO NOTHING RETURNING key",
                    (owner_id, idempotency_key, title, row["id"]),
                ).fetchone()
                if claimed is not None:
                    return CreateOutcome(
                        document=_to_document(row),
                        created=True,
                        requested_title=title,
                    )
                # Паралельний запит з тим самим ключем встиг першим:
                # скасовуємо свій документ і віддаємо його результат.
                raise psycopg.Rollback()
            winner = _find_by_key(conn, owner_id, idempotency_key)
            assert winner is not None  # nosec B101 — ключ щойно зайнято
            return winner

    def get(self, document_id: int) -> Document | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, title, access_mode, created_at, updated_at, "
                "deleted_at FROM documents WHERE id = %s",
                (document_id,),
            ).fetchone()
        return None if row is None else _to_document(row)

    def list_active(
        self, document_ids: Collection[int], limit: int, offset: int
    ) -> Page[Document]:
        ids = list(document_ids)
        if not ids:
            return Page(items=[], total=0)
        with self._pool.connection() as conn:
            total = conn.execute(
                "SELECT count(*) AS total FROM documents "
                "WHERE id = ANY(%s) AND deleted_at IS NULL",
                (ids,),
            ).fetchone()["total"]
            rows = conn.execute(
                "SELECT id, title, access_mode, created_at, updated_at, "
                "deleted_at FROM documents "
                "WHERE id = ANY(%s) AND deleted_at IS NULL "
                "ORDER BY id LIMIT %s OFFSET %s",
                (ids, limit, offset),
            ).fetchall()
        return Page(items=[_to_document(row) for row in rows], total=total)

    def list_trashed(
        self, document_ids: Collection[int], limit: int, offset: int
    ) -> Page[Document]:
        ids = list(document_ids)
        if not ids:
            return Page(items=[], total=0)
        with self._pool.connection() as conn:
            total = conn.execute(
                "SELECT count(*) AS total FROM documents "
                "WHERE id = ANY(%s) AND deleted_at IS NOT NULL",
                (ids,),
            ).fetchone()["total"]
            # За однакового часу видалення — порядок id, як у пам'яті.
            rows = conn.execute(
                "SELECT id, title, access_mode, created_at, updated_at, "
                "deleted_at FROM documents "
                "WHERE id = ANY(%s) AND deleted_at IS NOT NULL "
                "ORDER BY deleted_at DESC, id LIMIT %s OFFSET %s",
                (ids, limit, offset),
            ).fetchall()
        return Page(items=[_to_document(row) for row in rows], total=total)

    def update(
        self, document_id: int, change: Callable[[Document], Document]
    ) -> Document | None:
        with self._pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "SELECT id, title, access_mode, created_at, updated_at, "
                "deleted_at FROM documents WHERE id = %s FOR UPDATE",
                (document_id,),
            ).fetchone()
            if row is None:
                return None
            current = _to_document(row)
            updated = change(current)  # виняток тут → транзакція відкочена
            if updated.id != current.id:
                raise ValueError("update не може змінювати id документа.")
            conn.execute(
                "UPDATE documents SET title = %s, access_mode = %s, "
                "created_at = %s, updated_at = %s, deleted_at = %s "
                "WHERE id = %s",
                (
                    updated.title,
                    updated.access_mode.value,
                    updated.created_at,
                    updated.updated_at,
                    updated.deleted_at,
                    document_id,
                ),
            )
            return updated

    def purge_trashed_before(self, cutoff: datetime) -> list[int]:
        # Абзаци й ключі ідемпотентності видаляє ON DELETE CASCADE.
        with self._pool.connection() as conn:
            rows = conn.execute(
                "DELETE FROM documents "
                "WHERE deleted_at IS NOT NULL AND deleted_at <= %s "
                "RETURNING id",
                (cutoff,),
            ).fetchall()
        return sorted(row["id"] for row in rows)


class PostgresParagraphRepository:
    """Реалізує ``ParagraphRepository`` поверх таблиці paragraphs.

    Кожна зміна блокує рядок документа (``FOR UPDATE``), тож зміни
    абзаців одного документа виконуються по черзі й не рахують позиції
    з застарілих даних. Унікальність позицій перевіряється в кінці
    транзакції (DEFERRABLE), тому проміжні зсуви дозволені.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def list_for_document(self, document_id: int) -> list[Paragraph]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, document_id, position, content FROM paragraphs "
                "WHERE document_id = %s ORDER BY position",
                (document_id,),
            ).fetchall()
        return [_to_paragraph(row) for row in rows]

    def get(self, document_id: int, paragraph_id: int) -> Paragraph | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, document_id, position, content FROM paragraphs "
                "WHERE id = %s AND document_id = %s",
                (paragraph_id, document_id),
            ).fetchone()
        return None if row is None else _to_paragraph(row)

    def insert(
        self, document_id: int, position: int | None, content: str
    ) -> Paragraph:
        with self._pool.connection() as conn, conn.transaction():
            count = _lock_and_count(conn, document_id)
            target = count if position is None else position
            if target > count:
                raise InsertPositionError()
            conn.execute(
                "UPDATE paragraphs SET position = position + 1 "
                "WHERE document_id = %s AND position >= %s",
                (document_id, target),
            )
            row = conn.execute(
                "INSERT INTO paragraphs (document_id, position, content) "
                "VALUES (%s, %s, %s) "
                "RETURNING id, document_id, position, content",
                (document_id, target, content),
            ).fetchone()
            return _to_paragraph(row)

    def update(
        self,
        document_id: int,
        paragraph_id: int,
        content: str | None,
        position: int | None,
    ) -> Paragraph | None:
        with self._pool.connection() as conn, conn.transaction():
            count = _lock_and_count(conn, document_id)
            row = conn.execute(
                "SELECT position FROM paragraphs "
                "WHERE id = %s AND document_id = %s",
                (paragraph_id, document_id),
            ).fetchone()
            if row is None:
                return None
            old = row["position"]
            target = old if position is None else position
            if target >= count:
                raise MovePositionError()
            if target > old:  # униз: ті, що між, піднімаються на 1
                conn.execute(
                    "UPDATE paragraphs SET position = position - 1 "
                    "WHERE document_id = %s "
                    "AND position > %s AND position <= %s",
                    (document_id, old, target),
                )
            elif target < old:  # угору: ті, що між, опускаються на 1
                conn.execute(
                    "UPDATE paragraphs SET position = position + 1 "
                    "WHERE document_id = %s "
                    "AND position >= %s AND position < %s",
                    (document_id, target, old),
                )
            updated = conn.execute(
                "UPDATE paragraphs "
                "SET position = %s, content = COALESCE(%s, content) "
                "WHERE id = %s "
                "RETURNING id, document_id, position, content",
                (target, content, paragraph_id),
            ).fetchone()
            return _to_paragraph(updated)

    def delete(self, document_id: int, paragraph_id: int) -> bool:
        with self._pool.connection() as conn, conn.transaction():
            _lock_and_count(conn, document_id)
            row = conn.execute(
                "DELETE FROM paragraphs WHERE id = %s AND document_id = %s "
                "RETURNING position",
                (paragraph_id, document_id),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE paragraphs SET position = position - 1 "
                "WHERE document_id = %s AND position > %s",
                (document_id, row["position"]),
            )
            return True


def _find_by_key(
    conn: psycopg.Connection[Any], owner_id: UUID, idempotency_key: str
) -> CreateOutcome | None:
    row = conn.execute(
        "SELECT k.requested_title, d.id, d.title, d.access_mode, "
        "d.created_at, d.updated_at, d.deleted_at "
        "FROM idempotency_keys AS k "
        "JOIN documents AS d ON d.id = k.document_id "
        "WHERE k.user_id = %s AND k.key = %s",
        (owner_id, idempotency_key),
    ).fetchone()
    if row is None:
        return None
    return CreateOutcome(
        document=_to_document(row),
        created=False,
        requested_title=row["requested_title"],
    )


def _lock_and_count(conn: psycopg.Connection[Any], document_id: int) -> int:
    """Блокує документ до кінця транзакції й рахує його абзаци."""
    conn.execute(
        "SELECT id FROM documents WHERE id = %s FOR UPDATE", (document_id,)
    )
    return conn.execute(
        "SELECT count(*) AS total FROM paragraphs WHERE document_id = %s",
        (document_id,),
    ).fetchone()["total"]


def _to_document(row: dict[str, Any]) -> Document:
    return Document(
        id=row["id"],
        title=row["title"],
        access_mode=AccessMode(row["access_mode"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
    )


def _to_paragraph(row: dict[str, Any]) -> Paragraph:
    return Paragraph(
        id=row["id"],
        document_id=row["document_id"],
        position=row["position"],
        content=row["content"],
    )


# File was created by Claude. Reviewed by Kozynska Anastasia
