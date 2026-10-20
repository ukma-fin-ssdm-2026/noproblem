"""Граничні випадки створення документів і пагінації списків.

Кожен параметризований тест перевіряє значення *на межі* та *одразу за
нею*: саме там найчастіше трапляються помилки «на одиницю»
(off-by-one). Межі взято з контракту API (``src/api/main.py``):

* ``limit`` — від 1 до 100, ``offset`` — від 0;
* ``Idempotency-Key`` — від 1 до 128 символів;
* назва документа — до 100 символів, порожня означає «Без назви».
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import src.api.main as main_module
from tests.api.helpers import API, create_document, sign_up

DOCUMENTS = f"{API}/documents"
TRASH = f"{API}/documents/trash"
VALIDATION_ERROR = {"detail": "Некоректні вхідні дані."}

Headers = dict[str, str]


@pytest.fixture
def olena(client: TestClient) -> Headers:
    """Зареєстрована користувачка; повертає її заголовок авторизації."""
    return sign_up(client, "olena@example.com", "Олена")


@pytest.fixture
def make_documents(
    client: TestClient, olena: Headers
) -> Callable[[int], list[int]]:
    """Фабрика: створює ``n`` документів Олени й повертає їхні id."""

    def make(n: int) -> list[int]:
        return [
            create_document(client, olena, f"Документ {i}", key=f"key-{i}")
            for i in range(n)
        ]

    return make


def post_document(
    client: TestClient, who: Headers, key: str, body: dict | None = None
):
    """POST /documents з обов'язковим заголовком Idempotency-Key."""
    return client.post(
        DOCUMENTS, json=body, headers={**who, "Idempotency-Key": key}
    )


def total_documents(client: TestClient, who: Headers) -> int:
    response = client.get(DOCUMENTS, headers=who)
    return response.json()["pagination"]["total"]


# -- Пагінація -----------------------------------------------------------


@pytest.mark.parametrize("url", [DOCUMENTS, TRASH])
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": -1},
        {"offset": -1},
        {"limit": "abc"},
    ],
    ids=[
        "limit=0",
        "limit=101",
        "limit=-1",
        "offset=-1",
        "limit=not-a-number",
    ],
)
def test_pagination_out_of_range_is_rejected(
    client: TestClient, olena: Headers, url: str, params: dict
) -> None:
    response = client.get(url, params=params, headers=olena)
    assert response.status_code == 422
    assert response.json() == VALIDATION_ERROR


@pytest.mark.parametrize("url", [DOCUMENTS, TRASH])
@pytest.mark.parametrize("limit", [1, 100])
def test_pagination_limit_at_boundary_is_accepted(
    client: TestClient, olena: Headers, url: str, limit: int
) -> None:
    response = client.get(url, params={"limit": limit}, headers=olena)
    assert response.status_code == 200
    assert response.json()["pagination"]["limit"] == limit


def test_default_pagination_is_first_20(
    client: TestClient, olena: Headers
) -> None:
    pagination = client.get(DOCUMENTS, headers=olena).json()["pagination"]
    assert (pagination["limit"], pagination["offset"]) == (20, 0)


@pytest.mark.parametrize(
    ("offset", "expected_count", "has_more"),
    [
        (0, 2, True),  # перша сторінка, далі ще є
        (1, 2, False),  # остання повна сторінка
        (2, 1, False),  # останній елемент
        (3, 0, False),  # offset == total: порожньо, але не помилка
        (50, 0, False),  # далеко за кінцем списку
    ],
)
def test_offset_walks_through_the_list(
    client: TestClient,
    olena: Headers,
    make_documents: Callable[[int], list[int]],
    offset: int,
    expected_count: int,
    has_more: bool,
) -> None:
    ids = make_documents(3)
    response = client.get(
        DOCUMENTS, params={"limit": 2, "offset": offset}, headers=olena
    )
    body = response.json()
    assert [d["id"] for d in body["documents"]] == ids[offset : offset + 2]
    assert len(body["documents"]) == expected_count
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["has_more"] is has_more


def test_empty_list_has_no_more_pages(
    client: TestClient, olena: Headers
) -> None:
    body = client.get(DOCUMENTS, headers=olena).json()
    assert body["documents"] == []
    assert body["pagination"]["total"] == 0
    assert body["pagination"]["has_more"] is False


# -- Idempotency-Key ------------------------------------------------------


@pytest.mark.parametrize(
    ("length", "expected_status"),
    [(0, 422), (1, 201), (128, 201), (129, 422)],
)
def test_idempotency_key_length_boundaries(
    client: TestClient, olena: Headers, length: int, expected_status: int
) -> None:
    response = post_document(client, olena, "k" * length, {"title": "Т"})
    assert response.status_code == expected_status


def test_missing_idempotency_key_is_rejected(
    client: TestClient, olena: Headers
) -> None:
    response = client.post(DOCUMENTS, json={"title": "Т"}, headers=olena)
    assert response.status_code == 422
    assert response.json() == VALIDATION_ERROR


def test_replay_with_same_title_returns_original_document(
    client: TestClient, olena: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Повтор не створює дубль і рахується в метриці повторів.

    Справжній лічильник Prometheus глобальний для процесу, тож його
    значення залежить від інших тестів. Підміняємо його дублером
    (``Mock``) і перевіряємо рівно один виклик ``inc()``.
    """
    replays = Mock()
    monkeypatch.setattr(main_module, "IDEMPOTENT_REPLAYS", replays)

    first = post_document(client, olena, "same", {"title": "Звіт"})
    second = post_document(client, olena, "same", {"title": "Звіт"})

    assert second.status_code == 201
    assert second.json() == first.json()
    assert total_documents(client, olena) == 1
    replays.inc.assert_called_once_with()


def test_replay_with_different_title_is_conflict(
    client: TestClient, olena: Headers
) -> None:
    post_document(client, olena, "same", {"title": "Звіт"})
    response = post_document(client, olena, "same", {"title": "Інший"})
    assert response.status_code == 409
    assert "Idempotency-Key" in response.json()["detail"]
    assert total_documents(client, olena) == 1


def test_replay_without_body_matches_default_title(
    client: TestClient, olena: Headers
) -> None:
    """Без тіла й з порожньою назвою — однакова «Без назви»: не конфлікт."""
    first = post_document(client, olena, "same")
    second = post_document(client, olena, "same", {"title": ""})
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


# -- Назва документа ------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected_title"),
    [
        (None, "Без назви"),
        ({}, "Без назви"),
        ({"title": ""}, "Без назви"),
        ({"title": "   "}, "Без назви"),
        ({"title": "  План  "}, "План"),
        ({"title": "я" * 100}, "я" * 100),
    ],
    ids=["no-body", "empty-body", "empty", "spaces", "padded", "max-100"],
)
def test_title_is_normalized(
    client: TestClient, olena: Headers, body: dict | None, expected_title: str
) -> None:
    response = post_document(client, olena, "k", body)
    assert response.status_code == 201
    assert response.json()["title"] == expected_title


def test_title_over_100_characters_is_rejected(
    client: TestClient, olena: Headers
) -> None:
    response = post_document(client, olena, "k", {"title": "я" * 101})
    assert response.status_code == 422
    assert client.get(DOCUMENTS, headers=olena).json()["documents"] == []


# File was created by Claude. Reviewed by Kozynska Anastasia
