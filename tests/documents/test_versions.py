"""Знімки документа: політика версій і контракти сховищ."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.documents.adapters import (
    InMemoryDocumentRepository,
    InMemoryDocumentStore,
    InMemoryVersionRepository,
)
from src.documents.bootstrap import build_documents
from src.documents.models import DocumentVersion, VersionParagraph
from src.documents.postgres import (
    PostgresDocumentRepository,
    PostgresVersionRepository,
)
from src.documents.errors import DocumentNotFoundError
from src.iam.errors import AccessDeniedError
from tests.conftest import IamTestEnv

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
AUTHOR = UUID("00000000-0000-0000-0000-000000000001")
OTHER_AUTHOR = UUID("00000000-0000-0000-0000-000000000002")
THIRD_AUTHOR = UUID("00000000-0000-0000-0000-000000000003")
SNAPSHOT = (VersionParagraph(position=0, content="Перший"),)


@pytest.fixture(params=["memory", "postgres"])
def version_repository(request: pytest.FixtureRequest):
    if request.param == "memory":
        store = InMemoryDocumentStore()
        documents = InMemoryDocumentRepository(store)
        versions = InMemoryVersionRepository(store)
    else:
        pool = request.getfixturevalue("pg_pool")
        documents = PostgresDocumentRepository(pool)
        versions = PostgresVersionRepository(pool)
    document_id = documents.create(
        AUTHOR, "versions", "Версії", NOW
    ).document.id
    return document_id, documents, versions


def test_version_repository_adds_and_lists_newest_first(version_repository):
    document_id, _documents, versions = version_repository
    first = versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=AUTHOR,
            created_at=NOW,
            paragraphs=SNAPSHOT,
        )
    )
    assert first.paragraphs == SNAPSHOT
    assert versions.latest(document_id) == first

    second = versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=AUTHOR,
            created_at=NOW + timedelta(minutes=4),
            paragraphs=(VersionParagraph(position=0, content="Зміна"),),
        )
    )
    third = versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=OTHER_AUTHOR,
            created_at=NOW + timedelta(minutes=5),
            paragraphs=SNAPSHOT,
        )
    )

    assert versions.latest(document_id) == third
    page = versions.list(document_id, limit=1, offset=1)
    assert page.items == [second]
    assert page.total == 3


def test_purging_document_removes_its_versions(version_repository) -> None:
    document_id, documents, versions = version_repository
    versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=AUTHOR,
            created_at=NOW,
            paragraphs=SNAPSHOT,
        )
    )
    documents.update(
        document_id, lambda document: replace(document, deleted_at=NOW)
    )

    assert documents.purge_trashed_before(NOW) == [document_id]
    assert versions.latest(document_id) is None
    assert versions.list(document_id, limit=10, offset=0).total == 0


def test_purging_document_keeps_other_documents_versions(
    version_repository,
) -> None:
    document_id, documents, versions = version_repository
    other_id = documents.create(
        OTHER_AUTHOR, "other-versions", "Інший", NOW
    ).document.id
    versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=AUTHOR,
            created_at=NOW,
            paragraphs=SNAPSHOT,
        )
    )
    other_version = versions.add(
        DocumentVersion(
            id=0,
            document_id=other_id,
            author_id=OTHER_AUTHOR,
            created_at=NOW,
            paragraphs=(VersionParagraph(position=0, content="Інший"),),
        )
    )
    documents.update(
        document_id, lambda document: replace(document, deleted_at=NOW)
    )

    assert documents.purge_trashed_before(NOW) == [document_id]
    assert versions.latest(document_id) is None
    assert versions.latest(other_id) == other_version
    assert versions.list(other_id, limit=10, offset=0).total == 1


def test_version_ties_sort_by_id_descending(version_repository) -> None:
    document_id, _documents, versions = version_repository
    first = versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=AUTHOR,
            created_at=NOW,
            paragraphs=(VersionParagraph(position=0, content="Перший"),),
        )
    )
    second = versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=AUTHOR,
            created_at=NOW,
            paragraphs=(VersionParagraph(position=0, content="Другий"),),
        )
    )

    assert versions.latest(document_id) == second
    assert versions.list(document_id, limit=10, offset=0).items == [
        second,
        first,
    ]


def test_list_versions_returns_empty_page_past_total(
    version_repository,
) -> None:
    document_id, _documents, versions = version_repository
    versions.add(
        DocumentVersion(
            id=0,
            document_id=document_id,
            author_id=AUTHOR,
            created_at=NOW,
            paragraphs=SNAPSHOT,
        )
    )

    page = versions.list(document_id, limit=10, offset=100)
    assert page.items == []
    assert page.total == 1


def test_document_service_snapshots_paragraph_edits(
    env: IamTestEnv,
) -> None:
    module = build_documents(env.access, clock=env.clock)
    document_id = module.service.create(AUTHOR, "service", "Текст").document.id
    paragraph = module.service.add_paragraph(AUTHOR, document_id, "A", None)

    first = module.service.list_versions(
        AUTHOR, document_id, limit=10, offset=0
    )
    assert first.total == 1
    assert [item.content for item in first.items[0].paragraphs] == ["A"]

    env.clock.advance(minutes=4, seconds=59)
    module.service.update_paragraph(
        AUTHOR, document_id, paragraph.id, content="B", position=None
    )
    recent = module.service.list_versions(
        AUTHOR, document_id, limit=10, offset=0
    )
    assert recent.total == 1

    env.clock.advance(seconds=1)
    module.service.update_paragraph(
        AUTHOR, document_id, paragraph.id, content="C", position=None
    )
    env.access.grant_owner(document_id, OTHER_AUTHOR)
    env.clock.advance(seconds=1)
    module.service.update_paragraph(
        OTHER_AUTHOR, document_id, paragraph.id, content="D", position=None
    )
    versions = module.service.list_versions(
        AUTHOR, document_id, limit=2, offset=0
    )
    assert versions.total == 3
    assert [item.content for item in versions.items[0].paragraphs] == ["D"]
    assert [item.content for item in versions.items[1].paragraphs] == ["C"]
    older = module.service.list_versions(
        AUTHOR, document_id, limit=2, offset=2
    )
    assert older.total == 3
    assert [item.content for item in older.items[0].paragraphs] == ["A"]

    with pytest.raises(AccessDeniedError):
        module.service.list_versions(
            THIRD_AUTHOR, document_id, limit=10, offset=0
        )


def test_document_service_snapshots_multi_paragraph_moves_and_deletes(
    env: IamTestEnv,
) -> None:
    module = build_documents(env.access, clock=env.clock)
    document_id = module.service.create(AUTHOR, "multi", "Текст").document.id
    first = module.service.add_paragraph(AUTHOR, document_id, "A", None)

    env.clock.advance(minutes=5)
    inserted = module.service.add_paragraph(AUTHOR, document_id, "B", 0)

    env.clock.advance(minutes=5)
    module.service.update_paragraph(
        AUTHOR,
        document_id,
        inserted.id,
        content="C",
        position=1,
    )

    env.clock.advance(minutes=5)
    module.service.delete_paragraph(AUTHOR, document_id, first.id)

    env.clock.advance(minutes=5)
    module.service.delete_paragraph(AUTHOR, document_id, inserted.id)

    versions = module.service.list_versions(
        AUTHOR, document_id, limit=10, offset=0
    )
    assert versions.total == 5
    assert [
        (paragraph.position, paragraph.content)
        for paragraph in versions.items[0].paragraphs
    ] == []
    assert [
        (paragraph.position, paragraph.content)
        for paragraph in versions.items[1].paragraphs
    ] == [(0, "C")]
    assert [
        (paragraph.position, paragraph.content)
        for paragraph in versions.items[2].paragraphs
    ] == [(0, "A"), (1, "C")]
    assert [
        (paragraph.position, paragraph.content)
        for paragraph in versions.items[3].paragraphs
    ] == [(0, "B"), (1, "A")]
    assert [
        (paragraph.position, paragraph.content)
        for paragraph in versions.items[4].paragraphs
    ] == [(0, "A")]


def test_list_versions_rejects_document_in_trash(env: IamTestEnv) -> None:
    module = build_documents(env.access, clock=env.clock)
    document_id = module.service.create(AUTHOR, "trash", "Текст").document.id
    module.service.add_paragraph(AUTHOR, document_id, "A", None)
    module.service.move_to_trash(AUTHOR, document_id)

    with pytest.raises(DocumentNotFoundError):
        module.service.list_versions(AUTHOR, document_id, limit=10, offset=0)


def test_postgres_deduplication_at_exact_interval(
    env: IamTestEnv,
    pg_pool,
) -> None:
    env.clock.advance(microseconds=123456)
    module = build_documents(env.access, clock=env.clock, pool=pg_pool)
    document_id = module.service.create(
        AUTHOR, "pg-dedup", "Текст"
    ).document.id
    paragraph = module.service.add_paragraph(AUTHOR, document_id, "A", None)

    env.clock.advance(minutes=4, seconds=59, microseconds=999999)
    module.service.update_paragraph(
        AUTHOR, document_id, paragraph.id, content="B", position=None
    )
    assert (
        module.service.list_versions(
            AUTHOR, document_id, limit=10, offset=0
        ).total
        == 1
    )

    env.clock.advance(microseconds=1)
    module.service.update_paragraph(
        AUTHOR, document_id, paragraph.id, content="C", position=None
    )
    versions = module.service.list_versions(
        AUTHOR, document_id, limit=10, offset=0
    )
    assert versions.total == 2
    assert [item.content for item in versions.items[0].paragraphs] == ["C"]
