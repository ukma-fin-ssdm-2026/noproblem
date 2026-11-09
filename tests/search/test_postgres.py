"""PostgreSQL adapter tests for document search."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import logging
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
from psycopg_pool import PoolTimeout
import pytest

from src.documents.postgres import (
    PostgresDocumentRepository,
    PostgresParagraphRepository,
)
from src.search.errors import SearchUnavailableError
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
        {title_match.id, paragraph_match.id}, "100%", limit=20
    )
    paragraph_results = search.find_matches(
        {title_match.id, paragraph_match.id, trashed_match.id},
        "quarterly",
        limit=20,
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


def test_postgres_search_sets_timeout_and_passes_limit_to_query() -> None:
    pool = MagicMock()
    conn = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    conn.transaction.return_value.__enter__.return_value = None
    conn.execute.return_value.fetchall.return_value = []
    search = PostgresSearchRepository(pool)

    assert search.find_matches({1, 2}, "needle", limit=7) == []

    assert conn.execute.call_args_list[0].args == (
        "SET LOCAL statement_timeout = '2s'",
    )
    query, parameters = conn.execute.call_args_list[1].args
    assert "LIMIT %s" in query
    assert parameters[-1] == 7


@pytest.mark.parametrize(
    "failure",
    [
        psycopg.errors.QueryCanceled("statement timeout"),
        PoolTimeout("pool exhausted"),
    ],
)
def test_postgres_search_translates_only_expected_failures(
    failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    pool = MagicMock()
    conn = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    conn.transaction.return_value.__enter__.return_value = None
    if isinstance(failure, PoolTimeout):
        pool.connection.side_effect = failure
    else:
        conn.execute.side_effect = [None, failure]
    search = PostgresSearchRepository(pool)

    with caplog.at_level(logging.ERROR, logger="notely.search"):
        with pytest.raises(SearchUnavailableError) as raised:
            search.find_matches({1}, "needle", limit=20)

    assert raised.value.__cause__ is failure
    assert "Пошук у PostgreSQL тимчасово недоступний." in caplog.text


def test_postgres_search_does_not_translate_unexpected_errors() -> None:
    pool = MagicMock()
    conn = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    conn.transaction.return_value.__enter__.return_value = None
    conn.execute.side_effect = [None, RuntimeError("unexpected failure")]
    search = PostgresSearchRepository(pool)

    with pytest.raises(RuntimeError, match="unexpected failure"):
        search.find_matches({1}, "needle", limit=20)
