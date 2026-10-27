"""Юніт-тести ``DocumentService`` (без HTTP і без бази).

Сервіс збирається зі сховищами в пам'яті та підробленим годинником
IAM, тож час «перемотується» миттєво: перевірка правила «кошик
очищається через 30 днів» триває мілісекунди.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.documents.bootstrap import DocumentsModule, build_documents
from src.documents.errors import (
    DocumentNotFoundError,
    DocumentNotInTrashError,
    IdempotencyConflictError,
    InsertPositionError,
    MovePositionError,
    ParagraphNotFoundError,
)
from src.documents.models import AccessMode
from src.iam.errors import AccessDeniedError
from tests.conftest import IamTestEnv

OWNER = UUID("00000000-0000-0000-0000-000000000001")
STRANGER = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def module(env: IamTestEnv) -> DocumentsModule:
    return build_documents(env.access, clock=env.clock)


def create(module: DocumentsModule, title: str | None = "Документ") -> int:
    outcome = module.service.create(OWNER, str(uuid4()), title)
    return outcome.document.id


def contents(module: DocumentsModule, document_id: int) -> list[str]:
    paragraphs = module.service.list_paragraphs(OWNER, document_id)
    assert [p.position for p in paragraphs] == list(range(len(paragraphs)))
    return [p.content for p in paragraphs]


#
# Створення та ідемпотентність (FR-008–FR-010, FR-013)
#


def test_new_document_has_defaults_and_owner(
    module: DocumentsModule, env: IamTestEnv
) -> None:
    outcome = module.service.create(OWNER, "key", None)

    document = outcome.document
    assert outcome.created is True
    assert document.title == "Без назви"
    assert document.access_mode is AccessMode.RESTRICTED
    assert document.created_at == document.updated_at == env.clock.now()
    assert module.service.get(OWNER, document.id) == document


def test_replay_with_same_key_returns_same_document(
    module: DocumentsModule,
) -> None:
    first = module.service.create(OWNER, "key", "Звіт")
    second = module.service.create(OWNER, "key", "Звіт")

    assert second.created is False
    assert second.document == first.document
    assert module.service.list_active(OWNER, 20, 0).total == 1


def test_replay_with_other_title_is_conflict(module: DocumentsModule) -> None:
    module.service.create(OWNER, "key", "Звіт")
    with pytest.raises(IdempotencyConflictError):
        module.service.create(OWNER, "key", "Інший звіт")


def test_same_key_from_two_users_creates_two_documents(
    module: DocumentsModule,
) -> None:
    mine = module.service.create(OWNER, "key", "Звіт").document
    theirs = module.service.create(STRANGER, "key", "Звіт").document
    assert mine.id != theirs.id


#
# Права (I-11, NFR-SEC-001)
#


def test_stranger_is_denied_before_existence_is_revealed(
    module: DocumentsModule,
) -> None:
    document_id = create(module)
    for checked_id in (document_id, 999):
        with pytest.raises(AccessDeniedError):
            module.service.get(STRANGER, checked_id)


def test_lists_show_only_accessible_documents(
    module: DocumentsModule,
) -> None:
    create(module)
    assert module.service.list_active(STRANGER, 20, 0).total == 0
    assert module.service.list_trash(STRANGER, 20, 0).total == 0


#
# Кошик (FR-018–FR-023)
#


def test_trashed_document_leaves_active_list_and_can_be_restored(
    module: DocumentsModule, env: IamTestEnv
) -> None:
    document_id = create(module)
    module.service.move_to_trash(OWNER, document_id)

    assert module.service.list_active(OWNER, 20, 0).total == 0
    with pytest.raises(DocumentNotFoundError):
        module.service.get(OWNER, document_id)
    with pytest.raises(DocumentNotFoundError):
        module.service.rename(OWNER, document_id, "Нова")

    env.clock.advance(minutes=5)
    restored = module.service.restore(OWNER, document_id)
    assert restored.deleted_at is None
    assert restored.updated_at == env.clock.now()
    assert module.service.list_active(OWNER, 20, 0).total == 1


def test_active_document_cannot_be_restored(module: DocumentsModule) -> None:
    document_id = create(module)
    with pytest.raises(DocumentNotInTrashError):
        module.service.restore(OWNER, document_id)


def test_trash_lists_newest_first(
    module: DocumentsModule, env: IamTestEnv
) -> None:
    older, newer = create(module), create(module)
    module.service.move_to_trash(OWNER, older)
    env.clock.advance(minutes=1)
    module.service.move_to_trash(OWNER, newer)

    page = module.service.list_trash(OWNER, 20, 0)
    assert [document.id for document in page.items] == [newer, older]


@pytest.mark.parametrize(
    ("elapsed", "still_restorable"),
    [({"days": 29, "hours": 23}, True), ({"days": 30}, False)],
)
def test_trash_is_purged_after_30_days(
    module: DocumentsModule,
    env: IamTestEnv,
    elapsed: dict[str, float],
    still_restorable: bool,
) -> None:
    document_id = create(module)
    module.service.move_to_trash(OWNER, document_id)
    env.clock.advance(**elapsed)

    if still_restorable:
        module.service.restore(OWNER, document_id)
    else:
        with pytest.raises(DocumentNotInTrashError):
            module.service.restore(OWNER, document_id)
        assert module.documents.get(document_id) is None
        assert module.paragraphs.list_for_document(document_id) == []


#
# Абзаци (позиції завжди 0, 1, 2, … без пропусків)
#


def test_paragraphs_are_inserted_moved_and_deleted_in_order(
    module: DocumentsModule,
) -> None:
    document_id = create(module)
    service = module.service
    service.add_paragraph(OWNER, document_id, "b", None)
    first = service.add_paragraph(OWNER, document_id, "a", 0)
    service.add_paragraph(OWNER, document_id, "c", None)
    assert contents(module, document_id) == ["a", "b", "c"]

    moved = service.update_paragraph(OWNER, document_id, first.id, None, 2)
    assert moved.position == 2
    assert contents(module, document_id) == ["b", "c", "a"]

    service.update_paragraph(OWNER, document_id, first.id, "A", None)
    service.delete_paragraph(OWNER, document_id, moved.id)
    assert contents(module, document_id) == ["b", "c"]


def test_paragraph_positions_out_of_range_are_rejected(
    module: DocumentsModule,
) -> None:
    document_id = create(module)
    paragraph = module.service.add_paragraph(OWNER, document_id, "a", None)

    with pytest.raises(InsertPositionError):
        module.service.add_paragraph(OWNER, document_id, "x", 2)
    with pytest.raises(MovePositionError):
        module.service.update_paragraph(
            OWNER, document_id, paragraph.id, None, 1
        )


def test_missing_paragraph_is_not_found(module: DocumentsModule) -> None:
    document_id = create(module)
    with pytest.raises(ParagraphNotFoundError):
        module.service.get_paragraph(OWNER, document_id, 999)
    with pytest.raises(ParagraphNotFoundError):
        module.service.update_paragraph(OWNER, document_id, 999, "x", None)
    with pytest.raises(ParagraphNotFoundError):
        module.service.delete_paragraph(OWNER, document_id, 999)


def test_paragraph_change_bumps_document_updated_at(
    module: DocumentsModule, env: IamTestEnv
) -> None:
    document_id = create(module)
    env.clock.advance(minutes=3)
    module.service.add_paragraph(OWNER, document_id, "a", None)
    assert module.service.get(OWNER, document_id).updated_at == (
        env.clock.now()
    )


# File was created by Claude. Review pending: Kozynska Anastasia
