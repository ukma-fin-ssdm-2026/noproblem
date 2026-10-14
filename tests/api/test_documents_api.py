"""Прототип NoteLy через HTTP: документи + спільний доступ.

Головний тест — ``test_prototype_story``: він проходить увесь прототип
так, як це робили б реальні люди через вебклієнт. Решта тестів
перевіряє окремі правила, які в історію не вмістилися.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from tests.conftest import VALID_PASSWORD, IamTestEnv

API = "/api/v1"
MAX_PARAGRAPH_LENGTH = 10_000


def paragraphs_url(doc: int) -> str:
    return f"{API}/documents/{doc}/paragraphs"


def test_paragraph_over_limit_is_rejected_on_create(
    client: TestClient,
) -> None:
    """Занадто довгий текст абзацу відхиляється (CWE-770)."""
    olena = sign_up(client, "olena@example.com", "Олена")
    doc = create_document(client, olena, "Довгий текст")
    response = client.post(
        paragraphs_url(doc),
        json={"content": "a" * (MAX_PARAGRAPH_LENGTH + 1)},
        headers=olena,
    )
    assert response.status_code == 422
    listing = client.get(paragraphs_url(doc), headers=olena)
    assert listing.json()["paragraphs"] == []


def test_paragraph_over_limit_is_rejected_on_update(
    client: TestClient,
) -> None:
    olena = sign_up(client, "olena@example.com", "Олена")
    doc = create_document(client, olena, "Довгий текст")
    created = client.post(
        paragraphs_url(doc), json={"content": "Коротко"}, headers=olena
    )
    assert created.status_code == 201
    paragraph = f"{paragraphs_url(doc)}/{created.json()['id']}"
    response = client.patch(
        paragraph,
        json={"content": "a" * (MAX_PARAGRAPH_LENGTH + 1)},
        headers=olena,
    )
    assert response.status_code == 422
    assert client.get(paragraph, headers=olena).json()["content"] == "Коротко"


def test_paragraph_at_limit_is_accepted(client: TestClient) -> None:
    """Ліміт не ламає нормальні абзаци: рівно на межі текст приймається."""
    olena = sign_up(client, "olena@example.com", "Олена")
    doc = create_document(client, olena, "Межа")
    text = "a" * MAX_PARAGRAPH_LENGTH
    created = client.post(
        paragraphs_url(doc), json={"content": text}, headers=olena
    )
    assert created.status_code == 201
    paragraph = f"{paragraphs_url(doc)}/{created.json()['id']}"
    response = client.patch(paragraph, json={"content": text}, headers=olena)
    assert response.status_code == 200


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    # Лише ``iam``: так цей файл запускається і на старому коді з ``main``
    # (до виправлення), де тести мають впасти — регресійна перевірка.
    return TestClient(create_app(iam=env.iam))


def sign_up(client: TestClient, email: str, name: str) -> dict[str, str]:
    """Реєструє людину й повертає заголовок з її токеном."""
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "name": name, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_document(
    client: TestClient, who: dict[str, str], title: str, key: str = "k1"
) -> int:
    response = client.post(
        f"{API}/documents",
        json={"title": title},
        headers={**who, "Idempotency-Key": key},
    )
    assert response.status_code == 201
    return response.json()["id"]


def titles(client: TestClient, who: dict[str, str]) -> list[str]:
    response = client.get(f"{API}/documents", headers=who)
    assert response.status_code == 200
    return [document["title"] for document in response.json()["documents"]]


def test_prototype_story(client: TestClient) -> None:
    """Олена веде нотатки, ділиться ними з Андрієм, а Марко — сторонній."""
    # 1. Олена реєструється і створює документ — вона його власниця.
    olena = sign_up(client, "olena@example.com", "Олена")
    doc = create_document(client, olena, "План проєкту")
    paragraphs = f"{API}/documents/{doc}/paragraphs"

    # 2. Олена пише перший абзац.
    response = client.post(
        paragraphs, json={"content": "Зустріч у понеділок"}, headers=olena
    )
    assert response.status_code == 201
    paragraph = f"{paragraphs}/{response.json()['id']}"

    # 3. Андрій і Марко теж реєструються. Чужих документів вони не бачать.
    andrii = sign_up(client, "andrii@example.com", "Андрій")
    marko = sign_up(client, "marko@example.com", "Марко")
    assert titles(client, andrii) == []

    # 4. Олена ділиться документом з Андрієм як з редактором (FR-040).
    response = client.put(
        f"{API}/documents/{doc}/access",
        json={"email": "andrii@example.com", "role": "editor"},
        headers=olena,
    )
    assert response.status_code == 200
    andrii_id = response.json()["user_id"]

    # 5. Андрій бачить документ у своєму списку і редагує абзац.
    assert titles(client, andrii) == ["План проєкту"]
    response = client.patch(
        paragraph, json={"content": "Зустріч у вівторок"}, headers=andrii
    )
    assert response.status_code == 200

    # 6. Марко документа не бачить, а за прямим посиланням отримує 403.
    assert titles(client, marko) == []
    assert client.get(paragraphs, headers=marko).status_code == 403

    # 7. Марко не може сам видати собі доступ (NFR-SEC-004).
    response = client.put(
        f"{API}/documents/{doc}/access",
        json={"email": "marko@example.com", "role": "editor"},
        headers=marko,
    )
    assert response.status_code == 403

    # 8. Олена бачить зміни Андрія.
    response = client.get(paragraph, headers=olena)
    assert response.json()["content"] == "Зустріч у вівторок"

    # 9. Олена знижує Андрія до гостя: читати можна, редагувати — ні.
    client.put(
        f"{API}/documents/{doc}/access",
        json={"email": "andrii@example.com", "role": "guest"},
        headers=olena,
    )
    assert client.get(paragraph, headers=andrii).status_code == 200
    response = client.patch(paragraph, json={"content": "!"}, headers=andrii)
    assert response.status_code == 403

    # 10. Олена забирає доступ (FR-042): документ зникає в Андрія.
    response = client.delete(
        f"{API}/documents/{doc}/access/{andrii_id}", headers=olena
    )
    assert response.status_code == 204
    assert titles(client, andrii) == []
    assert client.get(paragraph, headers=andrii).status_code == 403


def test_without_token_documents_are_closed(client: TestClient) -> None:
    assert client.get(f"{API}/documents").status_code == 401


def test_missing_and_foreign_documents_look_the_same(
    client: TestClient,
) -> None:
    """Сторонній не може перебором дізнатися, які id існують."""
    olena = sign_up(client, "olena@example.com", "Олена")
    marko = sign_up(client, "marko@example.com", "Марко")
    doc = create_document(client, olena, "Особисте")
    foreign = client.get(f"{API}/documents/{doc}", headers=marko)
    missing = client.get(f"{API}/documents/999", headers=marko)
    assert foreign.status_code == missing.status_code == 403


def test_only_owner_trashes_and_restores(client: TestClient) -> None:
    """FR-019, FR-022: кошик — лише для власника."""
    olena = sign_up(client, "olena@example.com", "Олена")
    andrii = sign_up(client, "andrii@example.com", "Андрій")
    doc = create_document(client, olena, "Чернетка")
    client.put(
        f"{API}/documents/{doc}/access",
        json={"email": "andrii@example.com", "role": "editor"},
        headers=olena,
    )
    url = f"{API}/documents/{doc}"
    assert client.delete(url, headers=andrii).status_code == 403
    assert client.delete(url, headers=olena).status_code == 204

    trash = f"{API}/documents/trash"
    assert len(client.get(trash, headers=olena).json()["documents"]) == 1
    assert client.get(trash, headers=andrii).json()["documents"] == []
    assert client.post(f"{url}/restore", headers=andrii).status_code == 403
    assert client.post(f"{url}/restore", headers=olena).status_code == 200


def test_idempotency_key_is_per_user(client: TestClient) -> None:
    """Однаковий ключ від різних людей створює різні документи."""
    olena = sign_up(client, "olena@example.com", "Олена")
    andrii = sign_up(client, "andrii@example.com", "Андрій")
    first = create_document(client, olena, "Нотатки", key="same")
    second = create_document(client, andrii, "Нотатки", key="same")
    assert first != second
    assert titles(client, andrii) == ["Нотатки"]


# File was created by Claude. Reviewed by Kozynska Anastasia
