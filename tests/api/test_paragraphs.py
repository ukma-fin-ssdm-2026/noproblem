"""Абзаци документа: вставлення, переміщення, редагування, видалення.

Головний інваріант (див. ``src/api/main.py``): після будь-якої зміни
позиції абзаців ідуть підряд від 0 без пропусків, а ``updated_at``
документа оновлюється. Граничні позиції — 0, середина, ``len - 1``,
``len`` і ``len + 1`` — перевірено параметризованими тестами.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import API, create_document, paragraphs_url, sign_up
from tests.fakes import FakeClock

Headers = dict[str, str]


class Doc:
    """Документ Олени з трьома абзацами «A», «B», «C»."""

    def __init__(self, client: TestClient, who: Headers) -> None:
        self.client = client
        self.who = who
        self.id = create_document(client, who, "Абзаци")
        self.url = paragraphs_url(self.id)
        self.ids = {text: self.add(text).json()["id"] for text in "ABC"}

    def add(self, content: str, position: int | None = None):
        body: dict = {"content": content}
        if position is not None:
            body["position"] = position
        return self.client.post(self.url, json=body, headers=self.who)

    def item(self, text: str) -> str:
        return f"{self.url}/{self.ids[text]}"

    def listing(self) -> list[dict]:
        response = self.client.get(self.url, headers=self.who)
        assert response.status_code == 200
        return response.json()["paragraphs"]

    def contents(self) -> list[str]:
        paragraphs = self.listing()
        # Інваріант: позиції неперервні, від 0.
        assert [p["position"] for p in paragraphs] == list(
            range(len(paragraphs))
        )
        return [p["content"] for p in paragraphs]


@pytest.fixture
def olena(client: TestClient) -> Headers:
    return sign_up(client, "olena@example.com", "Олена")


@pytest.fixture
def doc(client: TestClient, olena: Headers) -> Doc:
    return Doc(client, olena)


# -- Вставлення -----------------------------------------------------------


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (0, ["X", "A", "B", "C"]),  # на початок
        (1, ["A", "X", "B", "C"]),  # у середину
        (3, ["A", "B", "C", "X"]),  # position == len: у кінець
        (None, ["A", "B", "C", "X"]),  # без позиції: у кінець
    ],
    ids=["start", "middle", "end", "default"],
)
def test_insert_at_valid_position(
    doc: Doc, position: int | None, expected: list[str]
) -> None:
    response = doc.add("X", position)
    assert response.status_code == 201
    assert response.json()["position"] == expected.index("X")
    assert doc.contents() == expected


@pytest.mark.parametrize("position", [4, 100, -1])
def test_insert_out_of_range_is_rejected(doc: Doc, position: int) -> None:
    assert doc.add("X", position).status_code == 422
    assert doc.contents() == ["A", "B", "C"]


@pytest.mark.parametrize(("position", "expected_status"), [(0, 201), (1, 422)])
def test_insert_into_empty_document(
    client: TestClient, olena: Headers, position: int, expected_status: int
) -> None:
    doc_id = create_document(client, olena, "Порожній", key="empty")
    response = client.post(
        paragraphs_url(doc_id),
        json={"content": "Перший", "position": position},
        headers=olena,
    )
    assert response.status_code == expected_status


def test_empty_content_is_allowed(doc: Doc) -> None:
    response = doc.add("")
    assert response.status_code == 201
    assert doc.contents() == ["A", "B", "C", ""]


# -- Переміщення та редагування ------------------------------------------


@pytest.mark.parametrize(
    ("text", "new_position", "expected"),
    [
        ("A", 2, ["B", "C", "A"]),  # перший → останній
        ("C", 0, ["C", "A", "B"]),  # останній → перший
        ("B", 1, ["A", "B", "C"]),  # на те саме місце
        ("A", 1, ["B", "A", "C"]),  # сусідня позиція
    ],
    ids=["first-to-last", "last-to-first", "same-place", "neighbour"],
)
def test_move_paragraph(
    doc: Doc, text: str, new_position: int, expected: list[str]
) -> None:
    response = doc.client.patch(
        doc.item(text), json={"position": new_position}, headers=doc.who
    )
    assert response.status_code == 200
    assert response.json()["position"] == new_position
    assert doc.contents() == expected


@pytest.mark.parametrize("new_position", [3, -1])
def test_move_out_of_range_is_rejected(doc: Doc, new_position: int) -> None:
    """Позиція ``len`` для переміщення вже поза межами (на відміну від
    вставлення, де ``len`` означає «у кінець»)."""
    response = doc.client.patch(
        doc.item("A"), json={"position": new_position}, headers=doc.who
    )
    assert response.status_code == 422
    assert doc.contents() == ["A", "B", "C"]


def test_edit_content_keeps_position(doc: Doc) -> None:
    response = doc.client.patch(
        doc.item("B"), json={"content": "B2"}, headers=doc.who
    )
    assert response.status_code == 200
    assert response.json()["position"] == 1
    assert doc.contents() == ["A", "B2", "C"]


def test_edit_content_and_move_together(doc: Doc) -> None:
    response = doc.client.patch(
        doc.item("C"), json={"content": "C2", "position": 0}, headers=doc.who
    )
    assert response.status_code == 200
    assert doc.contents() == ["C2", "A", "B"]


@pytest.mark.parametrize(
    "body",
    [{}, {"content": None, "position": None}],
    ids=["empty-body", "explicit-nulls"],
)
def test_patch_without_changes_is_rejected(doc: Doc, body: dict) -> None:
    response = doc.client.patch(doc.item("A"), json=body, headers=doc.who)
    assert response.status_code == 422
    assert response.json() == {"detail": "Некоректні вхідні дані."}


# -- Видалення ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A", ["B", "C"]),
        ("B", ["A", "C"]),
        ("C", ["A", "B"]),
    ],
    ids=["first", "middle", "last"],
)
def test_delete_renumbers_remaining(
    doc: Doc, text: str, expected: list[str]
) -> None:
    response = doc.client.delete(doc.item(text), headers=doc.who)
    assert response.status_code == 204
    assert doc.contents() == expected


def test_delete_all_leaves_empty_document(doc: Doc) -> None:
    for text in "ABC":
        doc.client.delete(doc.item(text), headers=doc.who)
    assert doc.contents() == []


def test_delete_twice_second_is_not_found(doc: Doc) -> None:
    first = doc.client.delete(doc.item("B"), headers=doc.who)
    second = doc.client.delete(doc.item("B"), headers=doc.who)
    assert (first.status_code, second.status_code) == (204, 404)


# -- Пошук абзацу ---------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_unknown_paragraph_is_not_found(doc: Doc, method: str) -> None:
    body = {"content": "Х"} if method == "PATCH" else None
    response = doc.client.request(
        method, f"{doc.url}/999", json=body, headers=doc.who
    )
    assert response.status_code == 404


def test_paragraph_of_another_document_is_not_found(
    client: TestClient, olena: Headers, doc: Doc
) -> None:
    """Id абзацу існує, але в іншому документі: 404, а не чужий абзац."""
    other = create_document(client, olena, "Інший", key="other")
    response = client.get(
        f"{paragraphs_url(other)}/{doc.ids['A']}", headers=olena
    )
    assert response.status_code == 404


@pytest.mark.parametrize("paragraph_id", [0, -1])
def test_non_positive_paragraph_id_is_rejected(
    doc: Doc, paragraph_id: int
) -> None:
    response = doc.client.get(f"{doc.url}/{paragraph_id}", headers=doc.who)
    assert response.status_code == 422


# -- Час зміни документа -------------------------------------------------


@pytest.mark.parametrize("action", ["add", "edit", "delete"])
def test_any_paragraph_change_bumps_document_updated_at(
    client: TestClient, olena: Headers, api_clock: FakeClock, action: str
) -> None:
    doc = Doc(client, olena)
    api_clock.advance(minutes=3)

    if action == "add":
        doc.add("D")
    elif action == "edit":
        client.patch(doc.item("A"), json={"content": "A2"}, headers=olena)
    else:
        client.delete(doc.item("A"), headers=olena)

    document = client.get(f"{API}/documents/{doc.id}", headers=olena).json()
    assert datetime.fromisoformat(document["updated_at"]) == api_clock.now()


# File was created by Claude. Reviewed by Kozynska Anastasia
