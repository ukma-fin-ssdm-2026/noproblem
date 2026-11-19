"""Спільні фікстури WebSocket-тестів Collab.

Усі з'єднання відкриваються з одного ``TestClient`` у режимі контекстного
менеджера: тоді всі WebSocket-сесії працюють в одному event loop, як і
під uvicorn, і розсилка між ними поводиться так само, як у продакшні.
Контекстний менеджер ще й запускає ``lifespan``, а там ``CollabEvents``
отримує event loop.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.api.main import create_app
from tests.api.helpers import create_document, paragraphs_url, sign_up
from tests.collab.helpers import Headers
from tests.conftest import IamTestEnv


@pytest.fixture
def client(
    env: IamTestEnv, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> Iterator[TestClient]:
    # lifespan записує OpenAPI-специфікацію: у тестах — у тимчасову теку.
    monkeypatch.setattr(main, "OPENAPI_PATH", tmp_path / "openapi.yaml")
    app = create_app(iam=env.iam, access=env.access, clock=env.clock)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def olena(client: TestClient) -> Headers:
    return sign_up(client, "olena@example.com", "Олена")


@pytest.fixture
def petro(client: TestClient) -> Headers:
    return sign_up(client, "petro@example.com", "Петро")


@pytest.fixture
def document_id(client: TestClient, olena: Headers) -> int:
    return create_document(client, olena, "Спільний")


@pytest.fixture
def paragraph_id(client: TestClient, olena: Headers, document_id: int) -> int:
    response = client.post(
        paragraphs_url(document_id), json={"content": "A"}, headers=olena
    )
    assert response.status_code == 201
    return response.json()["id"]


# File was created by Claude, verified by Kozynska Anastasia
