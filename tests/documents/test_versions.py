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
