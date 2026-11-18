"""Події IAM про зміну доступу (порт ``AccessEvents``, рішення 1).

Collab підписується на них, щоб одразу відключити людину, в якої
забрали доступ, або зняти блокування з того, кого понизили до Guest.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.iam import Action, Role, UserView
from src.iam.errors import AccessDeniedError
from tests.api.helpers import API, create_document, sign_up
from tests.conftest import VALID_PASSWORD, IamTestEnv

DOC = 1


class RecordingEvents:
    """Підробка отримувача: запам'ятовує всі виклики."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, UUID]] = []

    def access_changed(self, document_id: int, user_id: UUID) -> None:
        self.calls.append((document_id, user_id))


class BrokenEvents:
    """Отримувач, що падає: дія IAM однаково має завершитися."""

    def access_changed(self, document_id: int, user_id: UUID) -> None:
        raise RuntimeError("collab недоступний")


def user(env: IamTestEnv, email: str) -> UserView:
    return env.iam.register(email, email.split("@")[0], VALID_PASSWORD).user


@pytest.fixture
def events(env: IamTestEnv) -> RecordingEvents:
    recorder = RecordingEvents()
    env.access.bind_events(recorder)
    return recorder


@pytest.fixture
def owner(env: IamTestEnv) -> UserView:
    olena = user(env, "olena@example.com")
    env.access.grant_owner(DOC, olena.id)
    return olena


def test_share_to_new_member_notifies(
    env: IamTestEnv, owner: UserView, events: RecordingEvents
) -> None:
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.EDITOR)
    assert events.calls == [(DOC, andrii.id)]


def test_role_change_notifies(
    env: IamTestEnv, owner: UserView, events: RecordingEvents
) -> None:
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.EDITOR)
    env.access.share(owner.id, DOC, andrii.email, Role.GUEST)
    assert events.calls == [(DOC, andrii.id), (DOC, andrii.id)]


def test_revoke_notifies(
    env: IamTestEnv, owner: UserView, events: RecordingEvents
) -> None:
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.EDITOR)
    events.calls.clear()
    env.access.revoke(owner.id, DOC, andrii.id)
    assert events.calls == [(DOC, andrii.id)]


def test_denied_share_does_not_notify(
    env: IamTestEnv, owner: UserView, events: RecordingEvents
) -> None:
    andrii = user(env, "andrii@example.com")
    stranger = user(env, "stranger@example.com")
    with pytest.raises(AccessDeniedError):
        env.access.share(stranger.id, DOC, andrii.email, Role.EDITOR)
    assert events.calls == []


def test_without_events_nothing_breaks(
    env: IamTestEnv, owner: UserView
) -> None:
    """``events`` необов'язковий: без нього IAM працює як раніше."""
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.EDITOR)
    env.access.revoke(owner.id, DOC, andrii.id)
    assert not env.access.has_permission(andrii.id, DOC, Action.VIEW)


def test_broken_receiver_does_not_stop_revoke(
    env: IamTestEnv, owner: UserView
) -> None:
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.EDITOR)
    env.access.bind_events(BrokenEvents())
    env.access.revoke(owner.id, DOC, andrii.id)
    assert not env.access.has_permission(andrii.id, DOC, Action.VIEW)


# -- Запити на доступ (через API: потрібне сховище документів) ------------


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    return TestClient(
        create_app(iam=env.iam, access=env.access, clock=env.clock)
    )


def _request_access(
    client: TestClient,
) -> tuple[str, dict[str, str], int, UUID]:
    owner = sign_up(client, "owner@example.com", "Власник")
    requester = sign_up(client, "requester@example.com", "Запитувач")
    document_id = create_document(client, owner, "Приватні нотатки")
    url = f"{API}/documents/{document_id}/access/requests"
    submitted = client.post(url, headers=requester)
    assert submitted.status_code == 201
    requester_id = UUID(
        client.get(f"{API}/auth/me", headers=requester).json()["id"]
    )
    return f"{url}/{submitted.json()['id']}", owner, document_id, requester_id


def test_approved_request_notifies_requester(
    client: TestClient, events: RecordingEvents
) -> None:
    request_url, owner, document_id, requester_id = _request_access(client)
    response = client.post(f"{request_url}/approve", headers=owner)
    assert response.status_code == 200
    assert events.calls == [(document_id, requester_id)]


def test_rejected_request_does_not_notify(
    client: TestClient, events: RecordingEvents
) -> None:
    request_url, owner, _document_id, _requester_id = _request_access(client)
    response = client.post(f"{request_url}/reject", headers=owner)
    assert response.status_code == 200
    assert events.calls == []


# File was created by Claude, verified by Kozynska Anastasia
