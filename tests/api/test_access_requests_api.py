"""Інтеграційні сценарії запитів на доступ (FR-046–FR-051)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.helpers import API, create_document, sign_up


def access_url(document_id: int) -> str:
    return f"{API}/documents/{document_id}/access"


def test_access_denial_request_approval_grants_guest(
    client: TestClient,
) -> None:
    owner = sign_up(client, "owner@example.com", "Власник")
    requester = sign_up(client, "requester@example.com", "Запитувач")
    document_id = create_document(client, owner, "Приватні нотатки")
    url = access_url(document_id)
    document_url = f"{API}/documents/{document_id}"

    denied = client.get(document_url, headers=requester)
    assert denied.status_code == 403
    assert "надіслати запит" in denied.json()["detail"]

    submitted = client.post(f"{url}/requests", headers=requester)
    assert submitted.status_code == 201
    request = submitted.json()
    assert request["status"] == "pending"
    assert request["request_type"] == "access"

    duplicate = client.post(f"{url}/requests", headers=requester)
    assert duplicate.status_code == 409

    pending = client.get(f"{url}/requests", headers=owner)
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()["requests"]] == [
        request["id"]
    ]

    approved = client.post(
        f"{url}/requests/{request['id']}/approve", headers=owner
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client.get(document_url, headers=requester).status_code == 200

    members = client.get(url, headers=owner)
    guest = next(
        item
        for item in members.json()["members"]
        if item["email"] == "requester@example.com"
    )
    assert guest["role"] == "guest"

    second_approval = client.post(
        f"{url}/requests/{request['id']}/approve", headers=owner
    )
    assert second_approval.status_code == 409
    own_requests = client.get(f"{url}/requests/mine", headers=requester)
    assert own_requests.json()["requests"][0]["status"] == "approved"


def test_rejection_keeps_access_denied_and_allows_later_request(
    client: TestClient,
) -> None:
    owner = sign_up(client, "owner@example.com", "Власник")
    requester = sign_up(client, "requester@example.com", "Запитувач")
    document_id = create_document(client, owner, "Обмежений документ")
    url = access_url(document_id)
    document_url = f"{API}/documents/{document_id}"

    submitted = client.post(f"{url}/requests", headers=requester)
    request_id = submitted.json()["id"]
    rejected = client.post(
        f"{url}/requests/{request_id}/reject", headers=owner
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client.get(document_url, headers=requester).status_code == 403

    own_requests = client.get(f"{url}/requests/mine", headers=requester)
    assert own_requests.status_code == 200
    assert own_requests.json()["requests"][0]["status"] == "rejected"

    resubmitted = client.post(f"{url}/requests", headers=requester)
    assert resubmitted.status_code == 201
    assert resubmitted.json()["status"] == "pending"
    cannot_approve_rejected = client.post(
        f"{url}/requests/{request_id}/approve", headers=owner
    )
    assert cannot_approve_rejected.status_code == 409


def test_only_owner_can_list_or_review_access_requests(
    client: TestClient,
) -> None:
    owner = sign_up(client, "owner@example.com", "Власник")
    editor = sign_up(client, "editor@example.com", "Редактор")
    requester = sign_up(client, "requester@example.com", "Запитувач")
    document_id = create_document(client, owner, "Документ")
    url = access_url(document_id)
    invited = client.put(
        url,
        json={"email": "editor@example.com", "role": "editor"},
        headers=owner,
    )
    assert invited.status_code == 200
    submitted = client.post(f"{url}/requests", headers=requester)
    request_id = submitted.json()["id"]

    assert client.get(f"{url}/requests", headers=editor).status_code == 403
    assert (
        client.post(
            f"{url}/requests/{request_id}/approve", headers=editor
        ).status_code
        == 403
    )
    pending = client.get(f"{url}/requests", headers=owner)
    assert [item["id"] for item in pending.json()["requests"]] == [request_id]
