"""HTTP tests for calendar event routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests.api.helpers import API, create_document, sign_up

BASE = f"{API}/calendar/events"
START = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
END = START + timedelta(hours=1)


def create_event(
    client: TestClient, headers: dict[str, str], *, start=None, end=None
) -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "title": "Planning",
            "start_at": (start or START).isoformat(),
            "end_at": (end or END).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_calendar_routes_require_authentication(client: TestClient) -> None:
    response = client.get(
        BASE,
        params={"start_at": START.isoformat(), "end_at": END.isoformat()},
    )
    assert response.status_code == 401


def test_create_list_update_and_delete_event(client: TestClient) -> None:
    owner = sign_up(client, "calendar-owner@example.com", "Owner")
    created = create_event(client, owner)
    event_url = f"{BASE}/{created['id']}"

    listed = client.get(
        BASE,
        headers=owner,
        params={"start_at": START.isoformat(), "end_at": END.isoformat()},
    )
    assert listed.status_code == 200
    assert [event["id"] for event in listed.json()] == [created["id"]]

    updated = client.patch(event_url, headers=owner, json={"title": "Updated"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated"

    deleted = client.delete(event_url, headers=owner)
    assert deleted.status_code == 204
    assert client.get(event_url, headers=owner).status_code == 404


def test_invalid_event_interval_and_naive_time_are_rejected(
    client: TestClient,
) -> None:
    owner = sign_up(client, "calendar-invalid@example.com", "Owner")
    invalid_interval = client.post(
        BASE,
        headers=owner,
        json={
            "title": "Invalid",
            "start_at": START.isoformat(),
            "end_at": START.isoformat(),
        },
    )
    naive_time = client.post(
        BASE,
        headers=owner,
        json={
            "title": "Naive",
            "start_at": "2026-10-27T10:00:00",
            "end_at": "2026-10-27T11:00:00",
        },
    )
    assert invalid_interval.status_code == naive_time.status_code == 422


def test_only_event_participants_can_read_and_list_participants(
    client: TestClient,
) -> None:
    owner = sign_up(client, "calendar-owner-access@example.com", "Owner")
    participant = sign_up(
        client, "calendar-participant@example.com", "Participant"
    )
    stranger = sign_up(client, "calendar-stranger@example.com", "Stranger")
    created = create_event(client, owner)
    event_url = f"{BASE}/{created['id']}"

    added = client.put(
        f"{event_url}/participants",
        headers=owner,
        json={"email": "calendar-participant@example.com"},
    )
    assert added.status_code == 204

    listing = client.get(f"{event_url}/participants", headers=participant)
    assert listing.status_code == 200
    assert participant_user_id(client, participant) in listing.json()

    assert client.get(event_url, headers=stranger).status_code == 403
    assert (
        client.get(f"{event_url}/participants", headers=stranger).status_code
        == 403
    )
    unknown_email = client.put(
        f"{event_url}/participants",
        headers=stranger,
        json={"email": "not-registered@example.com"},
    )
    assert unknown_email.status_code == 403

    assert (
        client.delete(
            f"{event_url}/participants/me", headers=participant
        ).status_code
        == 204
    )
    assert client.get(event_url, headers=participant).status_code == 403


def test_creator_cannot_leave_and_can_remove_participant(
    client: TestClient,
) -> None:
    owner = sign_up(client, "calendar-owner-removal@example.com", "Owner")
    participant = sign_up(
        client, "calendar-member-removal@example.com", "Participant"
    )
    created = create_event(client, owner)
    event_url = f"{BASE}/{created['id']}"
    client.put(
        f"{event_url}/participants",
        headers=owner,
        json={"email": "calendar-member-removal@example.com"},
    )

    creator_leave = client.delete(
        f"{event_url}/participants/me", headers=owner
    )
    assert creator_leave.status_code == 403

    removed = client.delete(
        f"{event_url}/participants/{participant_user_id(client, participant)}",
        headers=owner,
    )
    assert removed.status_code == 204
    assert client.get(event_url, headers=participant).status_code == 403


def participant_user_id(
    client: TestClient, participant: dict[str, str]
) -> str:
    response = client.get(f"{API}/auth/me", headers=participant)
    if response.status_code == 200:
        return response.json()["id"]
    raise AssertionError(
        f"Unexpected profile response: {response.status_code}"
    )


def test_creator_can_link_and_unlink_document(client: TestClient) -> None:
    owner = sign_up(client, "calendar-doc-owner@example.com", "Owner")
    document_id = create_document(client, owner, "Meeting notes")
    created = create_event(client, owner)
    event_url = f"{BASE}/{created['id']}"

    linked = client.put(
        f"{event_url}/document",
        headers=owner,
        json={"document_id": document_id},
    )
    assert linked.status_code == 200
    assert linked.json()["document_id"] == document_id

    unlinked = client.delete(f"{event_url}/document", headers=owner)
    assert unlinked.status_code == 200
    assert unlinked.json()["document_id"] is None


def test_unknown_participant_email_returns_not_found(
    client: TestClient,
) -> None:
    owner = sign_up(client, "calendar-owner-unknown@example.com", "Owner")
    created = create_event(client, owner)
    response = client.put(
        f"{BASE}/{created['id']}/participants",
        headers=owner,
        json={"email": "nobody-calendar@example.com"},
    )
    assert response.status_code == 404

    malformed = client.put(
        f"{BASE}/{created['id']}/participants",
        headers=owner,
        json={"email": "invalid-email"},
    )
    assert malformed.status_code == 422


def test_creator_cannot_add_self_as_participant_by_email(
    client: TestClient,
) -> None:
    owner = sign_up(client, "calendar-owner-self-add@example.com", "Owner")
    created = create_event(client, owner)

    response = client.put(
        f"{BASE}/{created['id']}/participants",
        headers=owner,
        json={"email": "calendar-owner-self-add@example.com"},
    )

    assert response.status_code == 422


# File was created by Copilot and reviewed by Olha Marushchenko
