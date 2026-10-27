"""Спільні тести сховищ документів: у пам'яті та PostgreSQL.

Кожен тест виконується двічі — для ``InMemory…`` і ``Postgres…``
сховищ — і гарантує, що вони поводяться однаково: сервіс не має
помічати, з яким сховищем працює. Тести PostgreSQL пропускаються без
``TEST_DATABASE_URL``.

Перевіряється лише контракт сховища (порядок, сторінки, атомарність,
позиції абзаців, каскадне видалення). Правила сервісу — у тестах API.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.documents.adapters import (
    InMemoryDocumentRepository,
    InMemoryDocumentStore,
    InMemoryParagraphRepository,
)
from src.documents.errors import (
    DocumentNotFoundError,
    InsertPositionError,
    MovePositionError,
)
from src.documents.models import AccessMode, Document
from src.documents.ports import DocumentRepository, ParagraphRepository
from src.documents.postgres import (
    PostgresDocumentRepository,
    PostgresParagraphRepository,
)

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
ALICE = UUID("00000000-0000-0000-0000-00000000000a")
BOB = UUID("00000000-0000-0000-0000-00000000000b")


@dataclass
class Repositories:
    documents: DocumentRepository
    paragraphs: ParagraphRepository


@pytest.fixture(params=["memory", "postgres"])
def repos(request: pytest.FixtureRequest) -> Repositories:
    if request.param == "memory":
        store = InMemoryDocumentStore()
        return Repositories(
            InMemoryDocumentRepository(store),
            InMemoryParagraphRepository(store),
        )
    pool = request.getfixturevalue("pg_pool")
    return Repositories(
        PostgresDocumentRepository(pool), PostgresParagraphRepository(pool)
    )


def new_document(repos: Repositories, key: str) -> Document:
    return repos.documents.create(ALICE, key, "Звіт", NOW).document


def trash(repos: Repositories, document_id: int, at: datetime) -> None:
    repos.documents.update(document_id, lambda d: replace(d, deleted_at=at))


def contents(repos: Repositories, document_id: int) -> list[tuple[int, str]]:
    return [
        (paragraph.position, paragraph.content)
        for paragraph in repos.paragraphs.list_for_document(document_id)
    ]


def with_paragraphs(repos: Repositories, *texts: str) -> int:
    document_id = new_document(repos, "with-paragraphs").id
    for text in texts:
        repos.paragraphs.insert(document_id, None, text)
    return document_id


#
# Документи
#


def test_create_stores_new_restricted_document(repos: Repositories) -> None:
    outcome = repos.documents.create(ALICE, "key", "Звіт", NOW)

    document = outcome.document
    assert outcome.created is True
    assert outcome.requested_title == "Звіт"
    assert (document.title, document.access_mode) == (
        "Звіт",
        AccessMode.RESTRICTED,
    )
    assert document.created_at == document.updated_at == NOW
    assert document.deleted_at is None
    assert repos.documents.get(document.id) == document
    assert repos.documents.get(document.id + 1000) is None


def test_same_key_returns_first_document_per_user(
    repos: Repositories,
) -> None:
    first = repos.documents.create(ALICE, "key", "Звіт", NOW)
    replay = repos.documents.create(ALICE, "key", "Інша назва", NOW)
    other_user = repos.documents.create(BOB, "key", "Звіт", NOW)

    assert replay.created is False
    assert replay.document == first.document
    # Назва з першого запиту: за нею сервіс розпізнає конфлікт (409).
    assert replay.requested_title == "Звіт"
    assert other_user.created is True
    assert other_user.document.id != first.document.id


def test_list_active_filters_orders_and_paginates(
    repos: Repositories,
) -> None:
    first, second, trashed, _not_visible = (
        new_document(repos, key).id for key in ("a", "b", "c", "d")
    )
    trash(repos, trashed, NOW)
    visible = {first, second, trashed}  # четвертий документ — чужий

    page = repos.documents.list_active(visible, limit=20, offset=0)
    assert [d.id for d in page.items] == [first, second]
    assert page.total == 2

    second_page = repos.documents.list_active(visible, limit=1, offset=1)
    assert [d.id for d in second_page.items] == [second]
    assert second_page.total == 2
    assert repos.documents.list_active(set(), 20, 0).total == 0


def test_list_trashed_newest_first_and_ties_by_id(
    repos: Repositories,
) -> None:
    older, newest, same_time = (
        new_document(repos, key).id for key in ("a", "b", "c")
    )
    trash(repos, older, NOW)
    trash(repos, newest, NOW + timedelta(minutes=1))
    trash(repos, same_time, NOW)

    page = repos.documents.list_trashed(
        {older, newest, same_time}, limit=20, offset=0
    )
    assert [d.id for d in page.items] == [newest, older, same_time]
    assert page.total == 3


def test_update_is_atomic(repos: Repositories) -> None:
    document_id = new_document(repos, "key").id

    renamed = repos.documents.update(
        document_id, lambda d: replace(d, title="Нова")
    )
    assert renamed is not None and renamed.title == "Нова"
    assert repos.documents.get(document_id) == renamed

    def failing(_: Document) -> Document:
        raise DocumentNotFoundError(document_id)

    with pytest.raises(DocumentNotFoundError):
        repos.documents.update(document_id, failing)
    assert repos.documents.get(document_id) == renamed
    assert repos.documents.update(document_id + 1000, failing) is None


def test_purge_removes_expired_documents_with_their_data(
    repos: Repositories,
) -> None:
    cutoff = NOW - timedelta(days=30)
    expired = new_document(repos, "expired").id
    recent = new_document(repos, "recent").id
    active = new_document(repos, "active").id
    repos.paragraphs.insert(expired, None, "Текст")
    trash(repos, expired, cutoff)  # рівно на межі — видаляється
    trash(repos, recent, cutoff + timedelta(seconds=1))

    assert repos.documents.purge_trashed_before(cutoff) == [expired]

    assert repos.documents.get(expired) is None
    assert repos.paragraphs.list_for_document(expired) == []
    assert repos.documents.get(recent) is not None
    assert repos.documents.get(active) is not None
    # Ключ ідемпотентності видалено разом із документом.
    replay = repos.documents.create(ALICE, "expired", "Звіт", NOW)
    assert replay.created is True


#
# Абзаци: позиції завжди 0, 1, 2, … без пропусків
#


def test_insert_keeps_positions_contiguous(repos: Repositories) -> None:
    document_id = with_paragraphs(repos, "b")
    first = repos.paragraphs.insert(document_id, 0, "a")
    last = repos.paragraphs.insert(document_id, None, "c")

    assert (first.position, last.position) == (0, 2)
    assert contents(repos, document_id) == [(0, "a"), (1, "b"), (2, "c")]
    with pytest.raises(InsertPositionError):
        repos.paragraphs.insert(document_id, 4, "x")
    assert contents(repos, document_id) == [(0, "a"), (1, "b"), (2, "c")]


def test_update_moves_and_edits_paragraph(repos: Repositories) -> None:
    document_id = with_paragraphs(repos, "a", "b", "c")
    first_id = repos.paragraphs.list_for_document(document_id)[0].id

    moved = repos.paragraphs.update(document_id, first_id, None, 2)
    assert moved is not None and moved.position == 2
    assert contents(repos, document_id) == [(0, "b"), (1, "c"), (2, "a")]

    repos.paragraphs.update(document_id, first_id, "A", 0)
    assert contents(repos, document_id) == [(0, "A"), (1, "b"), (2, "c")]

    with pytest.raises(MovePositionError):
        repos.paragraphs.update(document_id, first_id, "x", 3)
    assert contents(repos, document_id) == [(0, "A"), (1, "b"), (2, "c")]
    missing_id = first_id + 1000
    assert repos.paragraphs.update(document_id, missing_id, "x", None) is None


def test_delete_closes_the_gap(repos: Repositories) -> None:
    document_id = with_paragraphs(repos, "a", "b", "c")
    middle_id = repos.paragraphs.list_for_document(document_id)[1].id

    assert repos.paragraphs.delete(document_id, middle_id) is True
    assert contents(repos, document_id) == [(0, "a"), (1, "c")]
    assert repos.paragraphs.delete(document_id, middle_id) is False


def test_paragraphs_belong_to_their_document(repos: Repositories) -> None:
    first_doc = with_paragraphs(repos, "a")
    second_doc = new_document(repos, "second").id
    paragraph = repos.paragraphs.insert(second_doc, None, "b")
    foreign_id = repos.paragraphs.list_for_document(first_doc)[0].id

    assert paragraph.position == 0  # позиції рахуються в межах документа
    assert repos.paragraphs.get(second_doc, paragraph.id) == paragraph
    assert repos.paragraphs.get(second_doc, foreign_id) is None
    assert repos.paragraphs.update(second_doc, foreign_id, "x", None) is None
    assert repos.paragraphs.delete(second_doc, foreign_id) is False
    assert contents(repos, first_doc) == [(0, "a")]


# File was created by Claude. Reviewed by Kozynska Anastasia
