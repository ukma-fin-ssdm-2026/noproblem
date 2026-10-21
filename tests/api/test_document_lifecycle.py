"""Життєвий цикл документа: читання, перейменування, кошик, відновлення.

Тут використано заглушку часу ``api_clock`` (див. ``conftest.py``):
вона робить ``created_at``/``updated_at``/``deleted_at`` передбачуваними,
тож тести перевіряють точні значення часу, а не «щось змінилося».
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.api.security import require_user
from tests.api.helpers import API, create_document, sign_up
from tests.fakes import FakeClock

Headers = dict[str, str]


def doc_url(doc: int) -> str:
    return f"{API}/documents/{doc}"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


@pytest.fixture
def olena(client: TestClient) -> Headers:
    return sign_up(client, "olena@example.com", "Олена")


@pytest.fixture
def doc(client: TestClient, olena: Headers) -> int:
    return create_document(client, olena, "План")


# -- Читання та перейменування -------------------------------------------


def test_owner_reads_own_document(
    client: TestClient, olena: Headers, doc: int
) -> None:
    response = client.get(doc_url(doc), headers=olena)
    assert response.status_code == 200
    assert response.json()["title"] == "План"
    assert response.json()["deleted_at"] is None


def test_rename_updates_title_and_timestamp(
    client: TestClient, olena: Headers, api_clock: FakeClock
) -> None:
    doc = create_document(client, olena, "План")
    created_at = api_clock.now()
    api_clock.advance(minutes=5)

    response = client.put(
        doc_url(doc), json={"title": "Новий план"}, headers=olena
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Новий план"
    assert parse_time(body["created_at"]) == created_at
    assert parse_time(body["updated_at"]) == api_clock.now()
    stored = client.get(doc_url(doc), headers=olena).json()
    assert stored["title"] == "Новий план"


@pytest.mark.parametrize(
    ("title", "expected_status"),
    [
        ("", 422),
        ("   ", 422),  # після обрізання пробілів назва порожня
        ("я", 200),  # мінімальна довжина
        ("я" * 100, 200),  # максимальна довжина
        ("я" * 101, 422),
    ],
    ids=["empty", "spaces", "len-1", "len-100", "len-101"],
)
def test_rename_title_length_boundaries(
    client: TestClient,
    olena: Headers,
    doc: int,
    title: str,
    expected_status: int,
) -> None:
    response = client.put(doc_url(doc), json={"title": title}, headers=olena)
    assert response.status_code == expected_status
    if expected_status == 422:
        stored = client.get(doc_url(doc), headers=olena).json()
        assert stored["title"] == "План"


@pytest.mark.parametrize(
    ("role", "expected_status"), [("editor", 200), ("guest", 403)]
)
def test_rename_requires_edit_permission(
    client: TestClient,
    olena: Headers,
    doc: int,
    role: str,
    expected_status: int,
) -> None:
    andrii = sign_up(client, "andrii@example.com", "Андрій")
    response = client.put(
        f"{doc_url(doc)}/access",
        json={"email": "andrii@example.com", "role": role},
        headers=olena,
    )
    assert response.status_code == 200
    response = client.put(doc_url(doc), json={"title": "Х"}, headers=andrii)
    assert response.status_code == expected_status


@pytest.mark.parametrize("doc_id", [0, -1])
def test_non_positive_document_id_is_rejected(
    client: TestClient, olena: Headers, doc_id: int
) -> None:
    response = client.get(doc_url(doc_id), headers=olena)
    assert response.status_code == 422


# -- Кошик і відновлення --------------------------------------------------


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("PUT", "", {"title": "Х"}),
        ("DELETE", "", None),
        ("GET", "/paragraphs", None),
        ("POST", "/paragraphs", {"content": "Х"}),
    ],
    ids=["read", "rename", "trash-again", "list-paragraphs", "add-paragraph"],
)
def test_trashed_document_is_not_active(
    client: TestClient,
    olena: Headers,
    doc: int,
    method: str,
    suffix: str,
    body: dict | None,
) -> None:
    """Документ у кошику «не існує» для звичайних операцій: 404."""
    assert client.delete(doc_url(doc), headers=olena).status_code == 204
    response = client.request(
        method, f"{doc_url(doc)}{suffix}", json=body, headers=olena
    )
    assert response.status_code == 404


def test_restoring_active_document_is_not_found(
    client: TestClient, olena: Headers, doc: int
) -> None:
    response = client.post(f"{doc_url(doc)}/restore", headers=olena)
    assert response.status_code == 404


def test_restore_twice_second_is_not_found(
    client: TestClient, olena: Headers, doc: int
) -> None:
    client.delete(doc_url(doc), headers=olena)
    first = client.post(f"{doc_url(doc)}/restore", headers=olena)
    second = client.post(f"{doc_url(doc)}/restore", headers=olena)
    assert (first.status_code, second.status_code) == (200, 404)
    assert first.json()["deleted_at"] is None


def test_trash_and_restore_record_exact_times(
    client: TestClient, olena: Headers, api_clock: FakeClock
) -> None:
    doc = create_document(client, olena, "План")
    api_clock.advance(minutes=10)
    client.delete(doc_url(doc), headers=olena)
    trashed = client.get(f"{API}/documents/trash", headers=olena).json()
    assert parse_time(trashed["documents"][0]["deleted_at"]) == (
        api_clock.now()
    )

    api_clock.advance(minutes=10)
    restored = client.post(f"{doc_url(doc)}/restore", headers=olena).json()
    assert parse_time(restored["updated_at"]) == api_clock.now()


def test_trash_lists_most_recently_deleted_first(
    client: TestClient, olena: Headers, api_clock: FakeClock
) -> None:
    older = create_document(client, olena, "Старіший", key="a")
    newer = create_document(client, olena, "Новіший", key="b")
    client.delete(doc_url(older), headers=olena)
    api_clock.advance(minutes=1)
    client.delete(doc_url(newer), headers=olena)

    trash = client.get(f"{API}/documents/trash", headers=olena).json()
    assert [d["id"] for d in trash["documents"]] == [newer, older]


def test_trash_document_is_removed_after_30_days(
    client: TestClient, olena: Headers, api_clock: FakeClock
) -> None:
    doc = create_document(client, olena, "Старий документ")
    assert client.delete(doc_url(doc), headers=olena).status_code == 204
    owner = client.app.state.iam.verify_session(
        olena["Authorization"].removeprefix("Bearer ")
    )
    api_clock.advance(days=30)
    client.app.dependency_overrides[require_user] = lambda: owner

    response = client.get(f"{API}/documents/trash", headers=olena)

    assert response.status_code == 200
    assert response.json()["documents"] == []


def test_idempotent_replay_does_not_return_expired_document(
    client: TestClient, olena: Headers, api_clock: FakeClock
) -> None:
    doc = create_document(client, olena, "Старий документ", key="expired")
    assert client.delete(doc_url(doc), headers=olena).status_code == 204
    owner = client.app.state.iam.verify_session(
        olena["Authorization"].removeprefix("Bearer ")
    )
    api_clock.advance(days=30)
    client.app.dependency_overrides[require_user] = lambda: owner

    response = client.post(
        f"{API}/documents",
        json={"title": "Старий документ"},
        headers={**olena, "Idempotency-Key": "expired"},
    )

    assert response.status_code == 201
    assert response.json()["id"] != doc
    assert response.json()["deleted_at"] is None


# File was created by Claude. Reviewed by Kozynska Anastasia
