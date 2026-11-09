"""Reliability tests for PostgreSQL search failure handling."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from src.api.search import get_search_service
from src.search.errors import SearchUnavailableError
from tests.api.helpers import API, sign_up


@pytest.mark.req("NFR-PERF-005")
def test_search_database_timeout_returns_503_without_internal_details(
    client: TestClient,
) -> None:
    user = sign_up(client, "search-timeout@example.com", "Search user")

    class UnavailableSearchService:
        def search(self, *, user_id, query):
            raise SearchUnavailableError()

    client.app.dependency_overrides[get_search_service] = (
        lambda: UnavailableSearchService()
    )

    response = client.get(
        f"{API}/search", params={"q": "quarterly"}, headers=user
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Пошук тимчасово недоступний. Спробуйте пізніше."
    }
