"""Unit tests for search matching and access filtering."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID

import pytest

from src.documents.models import AccessMode, Document, Page, Paragraph
from src.iam import Action
from src.iam.errors import AccessDeniedError
from src.search.service import SearchService

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
USER_ID = UUID("78c4bb56-c41d-4d64-8f78-5db3632f3480")


def document(document_id: int, title: str) -> Document:
    return Document(
        id=document_id,
        title=title,
        access_mode=AccessMode.RESTRICTED,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeDocumentRepository:
    """Fake repository filters by IDs and records active-document queries."""

    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.list_active_calls: list[tuple[Collection[int], int, int]] = []

    def list_active(
        self, document_ids: Collection[int], limit: int, offset: int
    ) -> Page[Document]:
        self.list_active_calls.append((document_ids, limit, offset))
        visible = [item for item in self.documents if item.id in document_ids]
        return Page(
            items=visible[offset : offset + limit],
            total=len(visible),
        )


class FakeParagraphRepository:
    """Fake repository returns paragraphs from an in-memory mapping."""

    def __init__(self, paragraphs: dict[int, list[Paragraph]]) -> None:
        self.paragraphs = paragraphs

    def list_for_document(self, document_id: int) -> list[Paragraph]:
        return self.paragraphs.get(document_id, [])


class FakeAccessService:
    """Fake IAM service records bulk access lookup and permission checks."""

    def __init__(
        self, document_ids: set[int], denied_ids: set[int] | None = None
    ) -> None:
        self.document_ids = document_ids
        self.denied_ids = denied_ids or set()
        self.accessible_ids_calls: list[UUID] = []
        self.permission_checks: list[tuple[int, Action]] = []

    def accessible_document_ids(self, user_id: UUID) -> set[int]:
        self.accessible_ids_calls.append(user_id)
        return self.document_ids

    def check(self, user_id: UUID, document_id: int, action: Action) -> None:
        self.permission_checks.append((document_id, action))
        if document_id in self.denied_ids:
            raise AccessDeniedError()


def make_service(
    documents: list[Document],
    paragraphs: dict[int, list[Paragraph]],
    accessible_ids: set[int],
    denied_ids: set[int] | None = None,
) -> tuple[SearchService, FakeDocumentRepository, FakeAccessService]:
    """Build a search service with fake repositories and IAM."""

    document_repo = FakeDocumentRepository(documents)
    access_service = FakeAccessService(accessible_ids, denied_ids)
    service = SearchService(
        document_repo=document_repo,
        paragraph_repo=FakeParagraphRepository(paragraphs),
        access_service=access_service,
    )
    return service, document_repo, access_service


@pytest.mark.req("FR-058")
@pytest.mark.req("FR-059")
def test_matches_title_and_paragraph_without_case_sensitivity() -> None:
    """FR-058/059: match titles and paragraph text without case sensitivity."""

    title_match = document(1, "Quarterly Orbit")
    paragraph_match = document(2, "Meeting notes")
    documents = [title_match, paragraph_match]
    paragraphs = {
        1: [Paragraph(1, 1, 0, "No title match here")],
        2: [Paragraph(2, 2, 0, "Notes about the ORBIT launch")],
    }
    service, _, _ = make_service(documents, paragraphs, {1, 2})

    title_results = service.search(user_id=USER_ID, query="qUaRtErLy")
    paragraph_results = service.search(user_id=USER_ID, query="orbit")

    assert [result.id for result in title_results] == [1]
    assert [result.id for result in paragraph_results] == [1, 2]


@pytest.mark.req("FR-062")
@pytest.mark.req("NFR-SEC-002")
def test_passes_only_accessible_ids_to_active_document_list() -> None:
    """FR-062/NFR-SEC-002: search only among IDs visible to the user."""

    documents = [document(1, "one"), document(2, "two"), document(3, "three")]
    access_ids = {1, 3}
    service, document_repo, access_service = make_service(
        documents, {}, access_ids
    )

    service.search(user_id=USER_ID, query="no match")

    assert document_repo.list_active_calls == [
        (access_ids, len(access_ids), 0)
    ]
    assert access_service.accessible_ids_calls == [USER_ID]
    assert access_service.permission_checks == []


@pytest.mark.req("NFR-PERF-005")
def test_search_uses_bulk_access_lookup_for_one_hundred_documents() -> None:
    """NFR-PERF-005: search 100 documents within 2s without N+1 ACL calls."""

    documents = [
        document(index, f"Document {index}") for index in range(1, 101)
    ]
    service, document_repo, access_service = make_service(
        documents, {}, {item.id for item in documents}
    )

    started_at = perf_counter()
    results = service.search(user_id=USER_ID, query="absent")
    elapsed = perf_counter() - started_at

    assert results == []
    assert elapsed < 2
    assert access_service.accessible_ids_calls == [USER_ID]
    assert access_service.permission_checks == []
    assert len(document_repo.list_active_calls) == 1


def test_search_checks_all_accessible_documents_before_limiting_results() -> (
    None
):
    """A match after the first 20 documents is not missed."""

    documents = [
        document(index, f"Document {index}") for index in range(1, 51)
    ]
    paragraphs = {35: [Paragraph(1, 35, 0, "The unique needle is here")]}
    accessible_ids = {item.id for item in documents}
    service, document_repo, _ = make_service(
        documents, paragraphs, accessible_ids
    )

    results = service.search(user_id=USER_ID, query="needle")

    assert [result.doc_id for result in results] == [35]
    assert document_repo.list_active_calls == [(accessible_ids, 50, 0)]


def test_match_access_checked_and_revoked_match_skipped() -> None:
    documents = [document(1, "Match one"), document(2, "Match two")]
    service, _, access_service = make_service(
        documents, {}, {1, 2}, denied_ids={1}
    )

    results = service.search(user_id=USER_ID, query="match")

    assert [result.doc_id for result in results] == [2]
    assert access_service.permission_checks == [
        (1, Action.VIEW),
        (2, Action.VIEW),
    ]


def test_search_limits_results_after_matching() -> None:
    """Return no more than 20 matches even when more documents match."""

    documents = [document(index, f"Match {index}") for index in range(1, 26)]
    service, _, _ = make_service(
        documents, {}, {item.id for item in documents}
    )

    results = service.search(user_id=USER_ID, query="match")

    assert [result.doc_id for result in results] == list(range(1, 21))


def test_paragraph_snippet_is_truncated_around_match() -> None:
    """Long paragraph snippets are bounded and retain the matching text."""

    content = f"{'a' * 400}needle{'b' * 400}"
    service, _, _ = make_service(
        [document(1, "Document")],
        {1: [Paragraph(1, 1, 0, content)]},
        {1},
    )

    result = service.search(user_id=USER_ID, query="needle")[0]

    assert len(result.snippet) <= 186
    assert result.snippet.startswith("...")
    assert result.snippet.endswith("...")
    assert "needle" in result.snippet
