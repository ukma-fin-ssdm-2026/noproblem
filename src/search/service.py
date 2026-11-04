"""Сервіс пошуку доступних активних документів."""

from __future__ import annotations

from uuid import UUID

from src.documents.ports import DocumentRepository, ParagraphRepository
from src.iam.access import AccessService
from src.iam.errors import AccessDeniedError
from src.iam.models import Action
from src.search.models import SearchMatch, SearchResult
from src.search.ports import SearchRepository

MAX_SEARCH_RESULTS = 20
SNIPPET_LENGTH = 180


class SearchService:
    """Шукає нечутливі до регістру збіги в назвах і абзацах."""

    def __init__(
        self,
        *,
        document_repo: DocumentRepository,
        paragraph_repo: ParagraphRepository,
        access_service: AccessService,
        search_repo: SearchRepository | None = None,
    ) -> None:
        self._document_repo = document_repo
        self._paragraph_repo = paragraph_repo
        self._access_service = access_service
        self._search_repo = search_repo

    def search(self, *, user_id: UUID, query: str) -> list[SearchResult]:
        """Повертає до 20 доступних активних документів, що містять запит.

        Для кожного результату ``snippet`` містить назву або перший
        абзац, у якому знайдено збіг.
        """
        accessible_ids = self._access_service.accessible_document_ids(user_id)
        if not accessible_ids:
            return []

        normalized_query = query.casefold()
        results: list[SearchResult] = []

        for match in self._find_matches(accessible_ids, query):
            try:
                self._access_service.check(user_id, match.doc_id, Action.VIEW)
            except AccessDeniedError:
                continue

            snippet = (
                match.matched_text
                if match.matched_text == match.title
                else _snippet_around_match(
                    match.matched_text, normalized_query
                )
            )
            if snippet is None:
                continue
            results.append(
                SearchResult(
                    doc_id=match.doc_id,
                    title=match.title,
                    snippet=snippet,
                )
            )
            if len(results) == MAX_SEARCH_RESULTS:
                break

        return results

    def _find_matches(
        self, accessible_ids: set[int], query: str
    ) -> list[SearchMatch]:
        if self._search_repo is not None:
            return self._search_repo.find_matches(accessible_ids, query)

        documents = self._document_repo.list_active(
            accessible_ids, limit=len(accessible_ids), offset=0
        )
        normalized_query = query.casefold()
        matches: list[SearchMatch] = []
        for document in documents.items:
            if normalized_query in document.title.casefold():
                matches.append(
                    SearchMatch(document.id, document.title, document.title)
                )
                continue
            for paragraph in self._paragraph_repo.list_for_document(
                document.id
            ):
                if normalized_query in paragraph.content.casefold():
                    matches.append(
                        SearchMatch(
                            document.id, document.title, paragraph.content
                        )
                    )
                    break
        return matches


def _snippet_around_match(content: str, normalized_query: str) -> str | None:
    normalized_content = content.casefold()
    match_start = normalized_content.find(normalized_query)
    if match_start < 0:
        return None
    if not normalized_query:
        return (
            content
            if len(content) <= SNIPPET_LENGTH
            else content[:SNIPPET_LENGTH] + "..."
        )

    source_offsets = [
        source_index
        for source_index, character in enumerate(content)
        for _ in character.casefold()
    ]
    source_match_start = source_offsets[match_start]
    center = (
        source_match_start + min(len(normalized_query), SNIPPET_LENGTH) // 2
    )
    start = max(
        0,
        min(
            center - SNIPPET_LENGTH // 2,
            len(content) - SNIPPET_LENGTH,
        ),
    )
    end = min(start + SNIPPET_LENGTH, len(content))

    return (
        ("..." if start > 0 else "")
        + content[start:end]
        + ("..." if end < len(content) else "")
    )
