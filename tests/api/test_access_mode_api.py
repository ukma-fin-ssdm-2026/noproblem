"""Інтеграційні сценарії режимів доступу (FR-044, FR-045, FR-052)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import API, create_document, sign_up


@pytest.mark.parametrize(
    ("role", "email"),
    [
        ("editor", "editor@example.com"),
        ("guest", "guest@example.com"),
    ],
)
def test_non_owner_cannot_change_access_mode(
    client: TestClient, role: str, email: str
) -> None:
    owner = sign_up(client, "owner@example.com", "Власник")
    member = sign_up(client, email, role)
    document_id = create_document(client, owner, "Обмежений документ")
    access_url = f"{API}/documents/{document_id}/access"
    invited = client.put(
        access_url,
        json={"email": email, "role": role},
        headers=owner,
    )
    assert invited.status_code == 200

    response = client.put(
        f"{access_url}/mode", json={"mode": "link"}, headers=member
    )
    assert response.status_code == 403
    document = client.get(f"{API}/documents/{document_id}", headers=owner)
    assert document.status_code == 200
    assert document.json()["access_mode"] == "restricted"


def test_link_mode_grants_guest_view_but_not_edit(
    client: TestClient,
) -> None:
    owner = sign_up(client, "owner@example.com", "Власник")
    stranger = sign_up(client, "stranger@example.com", "Сторонній")
    document_id = create_document(client, owner, "Документ за посиланням")
    access_url = f"{API}/documents/{document_id}/access"

    changed = client.put(
        f"{access_url}/mode", json={"mode": "link"}, headers=owner
    )
    assert changed.status_code == 200
    assert changed.json() == {"mode": "link"}

    viewed = client.get(f"{API}/documents/{document_id}", headers=stranger)
    assert viewed.status_code == 200
    assert viewed.json()["access_mode"] == "link"

    members = client.get(access_url, headers=owner)
    assert members.status_code == 200
    stranger_access = next(
        member
        for member in members.json()["members"]
        if member["email"] == "stranger@example.com"
    )
    assert stranger_access["role"] == "guest"

    edited = client.put(
        f"{API}/documents/{document_id}",
        json={"title": "Стороння зміна"},
        headers=stranger,
    )
    assert edited.status_code == 403
    unchanged = client.get(f"{API}/documents/{document_id}", headers=owner)
    assert unchanged.json()["title"] == "Документ за посиланням"
