"""Моделі результатів пошуку."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    """Один доступний документ, що відповідає пошуковому запиту."""

    doc_id: int
    title: str
    snippet: str

    @property
    def id(self) -> int:
        """Ідентифікатор у форматі, сумісному з моделлю Document."""
        return self.doc_id
