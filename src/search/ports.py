"""Порти сховища пошуку."""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from src.search.models import SearchMatch


class SearchRepository(Protocol):
    """Знаходить активні документи з відповідністю назви чи абзацу."""

    def find_matches(
        self, document_ids: Collection[int], query: str
    ) -> list[SearchMatch]:
        """Повертає збіги в порядку ідентифікаторів документів."""
        ...
