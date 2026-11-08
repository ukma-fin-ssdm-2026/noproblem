"""``DocumentService``: сценарії роботи з документами й абзацами.

Сервіс не знає ні про HTTP, ні про конкретне сховище: він працює
через порти ``DocumentRepository`` і ``ParagraphRepository`` та
перевіряє права через IAM перед КОЖНОЮ операцією (інтерфейс I-11).
Права перевіряються ДО пошуку документа: сторонній отримає 403 і для
чужого, і для неіснуючого id, тож не дізнається, які документи існують.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from src.documents.errors import (
    DocumentNotFoundError,
    DocumentNotInTrashError,
    IdempotencyConflictError,
    ParagraphNotFoundError,
)
from src.documents.models import CreateOutcome, Document, Page, Paragraph
from src.documents.ports import DocumentRepository, ParagraphRepository
from src.iam import AccessService, Action
from src.iam.ports import Clock

DEFAULT_TITLE = "Без назви"  # FR-010
TRASH_RETENTION = timedelta(days=30)  # FR-023


class DocumentService:
    """Документи, кошик і абзаци від імені конкретного користувача."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        paragraphs: ParagraphRepository,
        access: AccessService,
        clock: Clock,
    ) -> None:
        self._documents = documents
        self._paragraphs = paragraphs
        self._access = access
        self._clock = clock

    #
    # Документи
    #

    def create(
        self, user_id: UUID, idempotency_key: str, title: str | None
    ) -> CreateOutcome:
        """Створює документ або повертає вже створений з тим самим ключем.

        Без назви документ називається «Без назви» (FR-010), режим
        доступу — «Обмежений» (FR-009), автор стає власником (FR-008).

        Raises:
            IdempotencyConflictError: Ключ уже використаний з іншою
                назвою (FR-013).
        """
        now = self._clock.now()
        effective_title = title or DEFAULT_TITLE
        outcome = self._documents.create(
            user_id, idempotency_key, effective_title, now
        )
        if not outcome.created and _is_expired(outcome.document, now):
            # Ключ належить документу, який пролежав у кошику 30 днів, але
            # планувальник ще не встиг його видалити. Такий документ уже
            # вважається видаленим, тож повтор має створити новий. Робимо
            # те саме, що зробив би планувальник, і пробуємо ще раз. Це
            # рідкісний випадок (повтор ключа через місяць), тому звичайне
            # створення документа очищення кошика не запускає.
            self._documents.purge_trashed_before(now - TRASH_RETENTION)
            outcome = self._documents.create(
                user_id, idempotency_key, effective_title, now
            )
        if not outcome.created and outcome.requested_title != effective_title:
            raise IdempotencyConflictError()
        # Повтор надає роль ще раз: якщо після створення документа запис
        # ролі не встиг відбутися, повтор запиту це виправить.
        self._access.grant_owner(outcome.document.id, user_id)
        return outcome

    def list_active(
        self, user_id: UUID, limit: int, offset: int
    ) -> Page[Document]:
        """Сторінка активних документів, доступних користувачеві."""
        visible = self._access.accessible_document_ids(user_id)
        return self._documents.list_active(visible, limit, offset)

    def list_trash(
        self, user_id: UUID, limit: int, offset: int
    ) -> Page[Document]:
        """Сторінка кошика: документи, які користувач може відновити.

        Прострочені документи (30 днів і більше) не показуються, навіть
        якщо планувальник їх ще не видалив (FR-023).
        """
        restorable = {
            document_id
            for document_id in self._access.accessible_document_ids(user_id)
            if self._access.has_permission(user_id, document_id, Action.TRASH)
        }
        return self._documents.list_trashed(
            restorable,
            limit,
            offset,
            deleted_after=self._clock.now() - TRASH_RETENTION,
        )

    def get(self, user_id: UUID, document_id: int) -> Document:
        """Активний документ.

        Raises:
            AccessDeniedError: Немає права на перегляд.
            DocumentNotFoundError: Документа немає або він у кошику.
        """
        self._access.check(user_id, document_id, Action.VIEW)
        return self._require_active(document_id)

    def rename(self, user_id: UUID, document_id: int, title: str) -> Document:
        """Змінює назву активного документа (FR-014)."""
        self._access.check(user_id, document_id, Action.EDIT)
        now = self._clock.now()
        return self._change_active(
            document_id, lambda d: replace(d, title=title, updated_at=now)
        )

    def move_to_trash(self, user_id: UUID, document_id: int) -> Document:
        """М'яко видаляє документ: він переходить у кошик (FR-019)."""
        self._access.check(user_id, document_id, Action.TRASH)
        now = self._clock.now()
        return self._change_active(
            document_id, lambda d: replace(d, deleted_at=now, updated_at=now)
        )

    def restore(self, user_id: UUID, document_id: int) -> Document:
        """Повертає документ із кошика без зміни назви й вмісту (FR-020).

        Raises:
            AccessDeniedError: Не власник (FR-022).
            DocumentNotInTrashError: Документа немає в кошику або він
                пролежав там 30 днів і чекає на остаточне видалення.
        """
        self._access.check(user_id, document_id, Action.TRASH)
        now = self._clock.now()

        def restored(document: Document) -> Document:
            # Прострочений документ уже вважається видаленим, навіть
            # якщо планувальник ще не дійшов до нього (FR-023).
            if not document.is_trashed or _is_expired(document, now):
                raise DocumentNotInTrashError(document_id)
            return replace(document, deleted_at=None, updated_at=now)

        result = self._documents.update(document_id, restored)
        if result is None:
            raise DocumentNotInTrashError(document_id)
        return result

    #
    # Абзаци
    #

    def list_paragraphs(
        self, user_id: UUID, document_id: int
    ) -> list[Paragraph]:
        """Абзаци активного документа в порядку позицій."""
        self._access.check(user_id, document_id, Action.VIEW)
        self._require_active(document_id)
        return self._paragraphs.list_for_document(document_id)

    def get_paragraph(
        self, user_id: UUID, document_id: int, paragraph_id: int
    ) -> Paragraph:
        """Один абзац активного документа."""
        self._access.check(user_id, document_id, Action.VIEW)
        self._require_active(document_id)
        paragraph = self._paragraphs.get(document_id, paragraph_id)
        if paragraph is None:
            raise ParagraphNotFoundError(document_id, paragraph_id)
        return paragraph

    def add_paragraph(
        self,
        user_id: UUID,
        document_id: int,
        content: str,
        position: int | None,
    ) -> Paragraph:
        """Вставляє абзац; ``None`` — у кінець документа.

        Raises:
            InsertPositionError: Позиція більша за кількість абзаців.
        """
        self._access.check(user_id, document_id, Action.EDIT)
        self._require_active(document_id)
        paragraph = self._paragraphs.insert(document_id, position, content)
        self._touch(document_id)
        return paragraph

    def update_paragraph(
        self,
        user_id: UUID,
        document_id: int,
        paragraph_id: int,
        content: str | None,
        position: int | None,
    ) -> Paragraph:
        """Змінює текст і/або позицію абзацу.

        Raises:
            ParagraphNotFoundError: Абзацу немає в документі.
            MovePositionError: Нова позиція поза документом.
        """
        self._access.check(user_id, document_id, Action.EDIT)
        self._require_active(document_id)
        paragraph = self._paragraphs.update(
            document_id, paragraph_id, content, position
        )
        if paragraph is None:
            raise ParagraphNotFoundError(document_id, paragraph_id)
        self._touch(document_id)
        return paragraph

    def delete_paragraph(
        self, user_id: UUID, document_id: int, paragraph_id: int
    ) -> None:
        """Видаляє абзац; наступні зсуваються на одну позицію вгору."""
        self._access.check(user_id, document_id, Action.EDIT)
        self._require_active(document_id)
        if not self._paragraphs.delete(document_id, paragraph_id):
            raise ParagraphNotFoundError(document_id, paragraph_id)
        self._touch(document_id)

    #
    # Допоміжне
    #

    def _require_active(self, document_id: int) -> Document:
        document = self._documents.get(document_id)
        if document is None or document.is_trashed:
            raise DocumentNotFoundError(document_id)
        return document

    def _change_active(
        self, document_id: int, change: Callable[[Document], Document]
    ) -> Document:
        def guarded(document: Document) -> Document:
            if document.is_trashed:
                raise DocumentNotFoundError(document_id)
            return change(document)

        result = self._documents.update(document_id, guarded)
        if result is None:
            raise DocumentNotFoundError(document_id)
        return result

    def _touch(self, document_id: int) -> None:
        """Будь-яка зміна абзаців оновлює ``updated_at`` документа."""
        now = self._clock.now()
        self._documents.update(
            document_id, lambda d: replace(d, updated_at=now)
        )


def _is_expired(document: Document, now: datetime) -> bool:
    """Чи пролежав документ у кошику 30 днів або більше (FR-023).

    Межа та сама, що в ``purge_trashed_before``: документ, видалений
    рівно 30 днів тому, вже прострочений.
    """
    return (
        document.deleted_at is not None
        and document.deleted_at <= now - TRASH_RETENTION
    )


# File was created by Claude. Reviewed by Kozynska Anastasia
