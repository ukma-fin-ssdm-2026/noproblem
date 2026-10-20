"""Допоміжні функції для HTTP-тестів API.

Це звичайні функції, а не фікстури: їх викликають з параметрами
(хто, яка назва, який ключ), тож тест читається як сценарій.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import VALID_PASSWORD

API = "/api/v1"


def bearer(token: str) -> dict[str, str]:
    """Заголовок ``Authorization`` для токена."""
    return {"Authorization": f"Bearer {token}"}


def sign_up(client: TestClient, email: str, name: str) -> dict[str, str]:
    """Реєструє людину й повертає заголовок з її токеном."""
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "name": name, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return bearer(response.json()["access_token"])


def create_document(
    client: TestClient, who: dict[str, str], title: str, key: str = "k1"
) -> int:
    """Створює документ від імені ``who`` і повертає його id."""
    response = client.post(
        f"{API}/documents",
        json={"title": title},
        headers={**who, "Idempotency-Key": key},
    )
    assert response.status_code == 201
    return response.json()["id"]


def titles(client: TestClient, who: dict[str, str]) -> list[str]:
    """Назви документів, які бачить ``who``, у порядку списку."""
    response = client.get(f"{API}/documents", headers=who)
    assert response.status_code == 200
    return [document["title"] for document in response.json()["documents"]]


def paragraphs_url(doc: int) -> str:
    return f"{API}/documents/{doc}/paragraphs"


# File was created by Claude. Reviewed by Kozynska Anastasia
