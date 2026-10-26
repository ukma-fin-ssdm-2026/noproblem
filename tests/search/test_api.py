"""HTTP contract tests for document search.

These exercise FastAPI/Pydantic validation and response shapes, unlike
test_service.py, which covers search business logic.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from tests.api.helpers import API, create_document, paragraphs_url, sign_up


@pytest.mark.req("FR-061")
def test_one_character_query_is_rejected(client: TestClient) -> None:
    """FR-061: FastAPI rejects a too-short query before SearchService."""
    user = sign_up(client, "search@example.com", "Search user")

    response = client.get(f"{API}/search", params={"q": "x"}, headers=user)

    assert response.status_code == 422


@pytest.mark.req("FR-061")
def test_two_character_query_is_accepted(client: TestClient) -> None:
    """FR-061: accept the two-character boundary, even with no matches."""
    user = sign_up(client, "search@example.com", "Search user")

    response = client.get(f"{API}/search", params={"q": "xy"}, headers=user)

    assert response.status_code == 200


@pytest.mark.req("FR-060")
def test_no_matches_returns_empty_list(client: TestClient) -> None:
    """FR-060: return 200 + [] for no matches, not an error response."""
    user = sign_up(client, "search@example.com", "Search user")

    response = client.get(
        f"{API}/search", params={"q": "unmatched"}, headers=user
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.req("FR-058")
@pytest.mark.req("FR-059")
def test_search_returns_matching_document_title_and_paragraph(
    client: TestClient,
) -> None:
    user = sign_up(client, "search@example.com", "Search user")
    document_id = create_document(client, user, "Project notes")
    paragraph_response = client.post(
        paragraphs_url(document_id),
        json={"content": "The quarterly launch is next week."},
        headers=user,
    )
    assert paragraph_response.status_code == 201

    title_response = client.get(
        f"{API}/search", params={"q": "PROJECT"}, headers=user
    )
    content_response = client.get(
        f"{API}/search", params={"q": "quarterly"}, headers=user
    )

    assert title_response.status_code == 200
    assert title_response.json() == [
        {
            "doc_id": document_id,
            "title": "Project notes",
            "snippet": "Project notes",
        }
    ]
    assert content_response.status_code == 200
    assert content_response.json() == [
        {
            "doc_id": document_id,
            "title": "Project notes",
            "snippet": "The quarterly launch is next week.",
        }
    ]
