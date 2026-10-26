"""Tests for search domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.search.models import SearchResult


def test_search_result_stores_document_id_title_and_snippet() -> None:
    """SearchResult stores the document ID, title, and matching snippet."""

    result = SearchResult(
        doc_id=42,
        title="Release notes",
        snippet="The next release includes...",
    )

    assert (result.doc_id, result.title, result.snippet) == (
        42,
        "Release notes",
        "The next release includes...",
    )


def test_search_result_is_immutable() -> None:
    """SearchResult fields cannot be reassigned after construction."""

    result = SearchResult(doc_id=42, title="Release notes", snippet="...")

    with pytest.raises(FrozenInstanceError):
        result.title = "Updated title"  # type: ignore[misc]
