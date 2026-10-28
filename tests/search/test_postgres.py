"""PostgreSQL adapter tests for document search."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from src.documents.postgres import (
    PostgresDocumentRepository,
    PostgresParagraphRepository,
)
from src.search.postgres import PostgresSearchRepository

NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def test_postgres_search_matches_titles_paragraphs_and_literal_wildcards(
    pg_pool,
) -> None:
    documents = PostgresDocumentRepository(pg_pool)
    paragraphs = PostgresParagraphRepository(pg_pool)
    search = PostgresSearchRepository(pg_pool)
    owner_id = uuid4()

    title_match = documents.create(
        owner_id, "title", "Roadmap 100%", NOW
    ).document
    paragraph_match = documents.create(
        owner_id, "paragraph", "Meeting notes", NOW
    ).document
    trashed_match = documents.create(
        owner_id, "trashed", "Archived", NOW
    ).document
    paragraphs.insert(paragraph_match.id, None, "Prepare the QUARTERLY plan.")
    paragraphs.insert(trashed_match.id, None, "Quarterly archived")
    documents.update(
        trashed_match.id,
        lambda current: replace(current, deleted_at=NOW),
    )

    title_results = search.find_matches(
        {title_match.id, paragraph_match.id}, "100%"
    )
    paragraph_results = search.find_matches(
        {title_match.id, paragraph_match.id, trashed_match.id}, "quarterly"
    )

    assert [(item.doc_id, item.matched_text) for item in title_results] == [
        (title_match.id, "Roadmap 100%")
    ]
    assert [
        (item.doc_id, item.title, item.matched_text)
        for item in paragraph_results
    ] == [
        (
            paragraph_match.id,
            "Meeting notes",
            "Prepare the QUARTERLY plan.",
        )
    ]
