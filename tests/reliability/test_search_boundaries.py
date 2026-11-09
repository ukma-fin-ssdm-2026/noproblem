"""HTTP boundary tests for document search."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from tests.api.helpers import API, create_document, sign_up


@pytest.mark.req("FR-061")
@pytest.mark.parametrize(
    ("query_length", "expected_status"),
    [(1, 422), (2, 200), (10_001, 422)],
)
def test_query_length_boundaries(
    client: TestClient, query_length: int, expected_status: int
) -> None:
    user = sign_up(
        client,
        f"search-length-{query_length}@example.com",
        "Search user",
    )

    response = client.get(
        f"{API}/search",
        params={"q": "x" * query_length},
        headers=user,
    )

    assert response.status_code == expected_status


@pytest.mark.req("FR-061")
def test_query_at_maximum_length_is_accepted(client: TestClient) -> None:
    user = sign_up(client, "search-max-length@example.com", "Search user")

    response = client.get(
        f"{API}/search", params={"q": "x" * 10_000}, headers=user
    )

    assert response.status_code == 200
    assert response.json() == []


def test_search_returns_at_most_twenty_documents_over_http(
    client: TestClient,
) -> None:
    user = sign_up(client, "search-limit@example.com", "Search user")
    for index in range(25):
        create_document(
            client,
            user,
            f"Needle document {index}",
            key=f"search-limit-{index}",
        )

    response = client.get(
        f"{API}/search", params={"q": "needle"}, headers=user
    )

    assert response.status_code == 200
    assert len(response.json()) == 20
    assert all("Needle" in result["title"] for result in response.json())


@pytest.mark.req("FR-061")
@pytest.mark.parametrize(
    ("query", "matching_title", "other_title"),
    [
        ("%x", "Literal %x marker", "Literal _x marker"),
        ("_x", "Literal _x marker", "Literal %x marker"),
    ],
)
def test_percent_and_underscore_are_searched_literally_over_http(
    client: TestClient,
    query: str,
    matching_title: str,
    other_title: str,
) -> None:
    marker = "percent" if query.startswith("%") else "underscore"
    user = sign_up(
        client,
        f"search-literal-{marker}@example.com",
        "Search user",
    )
    create_document(
        client, user, matching_title, key=f"search-literal-match-{marker}"
    )
    create_document(
        client, user, other_title, key=f"search-literal-other-{marker}"
    )

    response = client.get(f"{API}/search", params={"q": query}, headers=user)

    assert response.status_code == 200
    assert [result["title"] for result in response.json()] == [matching_title]
