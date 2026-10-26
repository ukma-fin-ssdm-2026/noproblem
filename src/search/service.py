"""Сервіс пошуку доступних активних документів."""

from __future__ import annotations

from uuid import UUID

from src.documents.ports import DocumentRepository, ParagraphRepository
from src.iam.access import AccessService
from src.search.models import SearchResult


class SearchService:
    """Шукає нечутливі до регістру збіги в назвах і абзацах."""

    def __init__(
        self,
        *,
        document_repo: DocumentRepository,
        paragraph_repo: ParagraphRepository,
        access_service: AccessService,
    ) -> None:
        self._document_repo = document_repo
        self._paragraph_repo = paragraph_repo
        self._access_service = access_service

    def search(self, *, user_id: UUID, query: str) -> list[SearchResult]:
        """Повертає до 20 доступних активних документів, що містять запит.

        Для кожного результату ``snippet`` містить назву або перший
        абзац, у якому знайдено збіг.
        """
        accessible_ids = self._access_service.accessible_document_ids(user_id)
        if not accessible_ids:
            return []

        documents = self._document_repo.list_active(
            accessible_ids, limit=20, offset=0
        )
        normalized_query = query.casefold()
        results: list[SearchResult] = []

        for document in documents.items:
            snippet = (
                document.title
                if normalized_query in document.title.casefold()
                else None
            )
            if snippet is None:
                for paragraph in self._paragraph_repo.list_for_document(
                    document.id
                ):
                    if normalized_query in paragraph.content.casefold():
                        snippet = paragraph.content
                        break

            if snippet is not None:
                results.append(
                    SearchResult(
                        doc_id=document.id,
                        title=document.title,
                        snippet=snippet,
                    )
                )

        return results
