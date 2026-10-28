"""Моделі результатів пошуку."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchMatch:
    """Документ і текстова частина, у якій знайдено збіг."""

    doc_id: int
    title: str
    matched_text: str


@dataclass(frozen=True)
class SearchResult:
    """Один доступний документ, що відповідає пошуковому запиту."""

    doc_id: int
    title: str
    snippet: str

    @property
    def id(self) -> int:
        """Аліас для сумісності з кодом, що працює з моделлю Document."""
        return self.doc_id
