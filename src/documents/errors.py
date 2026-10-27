"""Винятки модуля «Документи».

Модуль не знає про HTTP: перетворення винятку на статус і текст
відповіді (404, 409, 422) робить API-адаптер ``src/api/documents.py``,
як у модулі IAM. Винятки несуть ідентифікатори, щоб адаптер міг
скласти точне повідомлення.
"""

from __future__ import annotations


class DocumentsError(Exception):
    """Базовий виняток модуля «Документи»."""


class DocumentNotFoundError(DocumentsError):
    """Активного документа з таким id немає (або він у кошику)."""

    def __init__(self, document_id: int) -> None:
        super().__init__(f"Active document {document_id} not found.")
        self.document_id = document_id


class DocumentNotInTrashError(DocumentsError):
    """Документа з таким id немає в кошику (FR-020)."""

    def __init__(self, document_id: int) -> None:
        super().__init__(f"Document {document_id} is not in trash.")
        self.document_id = document_id


class ParagraphNotFoundError(DocumentsError):
    """У документі немає абзацу з таким id."""

    def __init__(self, document_id: int, paragraph_id: int) -> None:
        super().__init__(
            f"Paragraph {paragraph_id} not found in document {document_id}."
        )
        self.document_id = document_id
        self.paragraph_id = paragraph_id


class IdempotencyConflictError(DocumentsError):
    """Ключ ідемпотентності повторено з іншою назвою (FR-013)."""


class ParagraphPositionError(DocumentsError):
    """Позиція абзацу виходить за межі документа."""


class InsertPositionError(ParagraphPositionError):
    """Позиція вставлення більша за кількість абзаців."""


class MovePositionError(ParagraphPositionError):
    """Нова позиція абзацу поза наявними позиціями."""


# File was created by Claude. Reviewed by Kozynska Anastasia
