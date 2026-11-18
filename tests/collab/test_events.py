"""Події документів і IAM у Collab (``CollabEvents``, рішення 1 і 3).

Зміни йдуть через REST, а співредактори дізнаються про них через
WebSocket: ``document.changed``, закриття з 4403 / 4404, зняття
блокувань після зниження ролі.
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.collab.connections import (
    Connection,
    ConnectionManager,
    close_quietly,
)
from src.collab.events import CollabEvents
from src.collab.locks import LockManager
from src.iam import Role
from tests.api.helpers import API, paragraphs_url
from tests.collab.helpers import (
    Headers,
    assert_quiet,
    close_code,
    joined,
    share,
    user_id,
)


def document_changed(kind: str, author: str) -> dict[str, str]:
    return {"type": "document.changed", "kind": kind, "author_id": author}


def wait_for_role(
    client: TestClient, document_id: int, who: str, role: Role
) -> None:
    """Чекає, поки Collab оновить роль (про підвищення нічого не шле)."""
    connections = client.app.state.connections
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        found = connections.connections_of(document_id, UUID(who))
        if found and all(c.role is role for c in found):
            return
        time.sleep(0.01)
    raise AssertionError(f"роль не стала {role.value}")


# -- document.changed ------------------------------------------------------


def test_added_paragraph_notifies_everyone_including_author(
    client: TestClient, olena: Headers, petro: Headers, document_id: int
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    with joined(client, document_id, olena) as ws_olena:
        with joined(client, document_id, petro) as ws_petro:
            ws_olena.receive_json()  # presence: joined
            response = client.post(
                paragraphs_url(document_id),
                json={"content": "Новий"},
                headers=olena,
            )
            assert response.status_code == 201
            expected = document_changed("paragraphs", user_id(client, olena))
            assert ws_olena.receive_json() == expected
            assert ws_petro.receive_json() == expected


@pytest.mark.parametrize("action", ["delete", "move"])
def test_deleted_or_moved_paragraph_notifies(
    client: TestClient,
    olena: Headers,
    document_id: int,
    paragraph_id: int,
    action: str,
) -> None:
    second = client.post(
        paragraphs_url(document_id), json={"content": "B"}, headers=olena
    ).json()["id"]
    url = f"{paragraphs_url(document_id)}/{second}"
    with joined(client, document_id, olena) as ws:
        if action == "delete":
            response = client.delete(url, headers=olena)
        else:
            response = client.patch(url, json={"position": 0}, headers=olena)
        assert response.status_code in (200, 204)
        message = ws.receive_json()
        assert (message["type"], message["kind"]) == (
            "document.changed",
            "paragraphs",
        )


def test_text_only_edit_sends_no_event(
    client: TestClient, olena: Headers, document_id: int, paragraph_id: int
) -> None:
    """Текст розсилає paragraph.edit; REST-збереження подій не дає."""
    with joined(client, document_id, olena) as ws:
        response = client.patch(
            f"{paragraphs_url(document_id)}/{paragraph_id}",
            json={"content": "Інший текст"},
            headers=olena,
        )
        assert response.status_code == 200
        assert_quiet(ws)


def test_rename_notifies_title(
    client: TestClient, olena: Headers, document_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        response = client.put(
            f"{API}/documents/{document_id}",
            json={"title": "Нова назва"},
            headers=olena,
        )
        assert response.status_code == 200
        assert ws.receive_json() == document_changed(
            "title", user_id(client, olena)
        )


def test_trash_notifies_then_closes_everyone_with_4404(
    client: TestClient, olena: Headers, petro: Headers, document_id: int
) -> None:
    share(client, olena, document_id, "petro@example.com", "guest")
    with joined(client, document_id, olena) as ws_olena:
        with joined(client, document_id, petro) as ws_petro:
            ws_olena.receive_json()  # presence: joined
            response = client.delete(
                f"{API}/documents/{document_id}", headers=olena
            )
            assert response.status_code == 204
            for ws in (ws_olena, ws_petro):
                assert ws.receive_json()["kind"] == "trashed"
                assert close_code(ws) == 4404


# -- Зміна доступу ---------------------------------------------------------


def test_revoked_member_is_closed_with_4403_and_locks_released(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    petro_id = user_id(client, petro)
    with joined(client, document_id, olena) as ws_olena:
        with joined(client, document_id, petro) as ws_petro:
            ws_olena.receive_json()  # presence: joined
            ws_petro.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            ws_petro.receive_json()  # lock.granted
            ws_petro.receive_json()  # lock.changed
            ws_olena.receive_json()  # lock.changed
            response = client.delete(
                f"{API}/documents/{document_id}/access/{petro_id}",
                headers=olena,
            )
            assert response.status_code == 204
            assert close_code(ws_petro) == 4403
        assert ws_olena.receive_json() == {
            "type": "lock.changed",
            "paragraph_id": paragraph_id,
            "user_id": None,
        }
        left = ws_olena.receive_json()
        assert (left["type"], left["status"]) == ("presence", "left")
    assert client.app.state.lock_manager.locks(document_id) == {}


def test_demoted_editor_loses_locks_but_stays_connected(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    with joined(client, document_id, olena) as ws_olena:
        with joined(client, document_id, petro) as ws_petro:
            ws_olena.receive_json()  # presence: joined
            ws_petro.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            ws_petro.receive_json()  # lock.granted
            ws_petro.receive_json()  # lock.changed
            ws_olena.receive_json()  # lock.changed

            share(client, olena, document_id, "petro@example.com", "guest")
            released = {
                "type": "lock.changed",
                "paragraph_id": paragraph_id,
                "user_id": None,
            }
            assert ws_olena.receive_json() == released
            assert ws_petro.receive_json() == released

            # Закешована роль оновилася: курсори тепер заборонені.
            ws_petro.send_json(
                {"type": "cursor", "paragraph_id": paragraph_id, "offset": 0}
            )
            error = ws_petro.receive_json()
            assert (error["type"], error["code"]) == ("error", "forbidden")


def test_promoted_guest_can_send_cursor_without_reconnect(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "guest")
    with joined(client, document_id, olena) as ws_olena:
        with joined(client, document_id, petro) as ws_petro:
            ws_olena.receive_json()  # presence: joined
            share(client, olena, document_id, "petro@example.com", "editor")
            wait_for_role(
                client, document_id, user_id(client, petro), Role.EDITOR
            )
            ws_petro.send_json(
                {"type": "cursor", "paragraph_id": paragraph_id, "offset": 1}
            )
            assert ws_olena.receive_json()["type"] == "cursor"


def test_access_change_of_absent_user_does_nothing(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
) -> None:
    """Петра немає в документі: його понизили — Олені нічого не шлють."""
    share(client, olena, document_id, "petro@example.com", "editor")
    with joined(client, document_id, olena) as ws:
        share(client, olena, document_id, "petro@example.com", "guest")
        assert_quiet(ws)


# -- Без event loop і повторне закриття ------------------------------------


def test_events_without_loop_are_ignored(client: TestClient) -> None:
    """Застосунок без lifespan: події просто пропускаються."""
    events = CollabEvents(
        ConnectionManager(), LockManager(), client.app.state.access
    )
    author = UUID(int=1)
    events.changed(1, "paragraphs", author)
    events.access_changed(1, author)
    events.attach(asyncio.new_event_loop())
    events.detach()
    events.changed(1, "title", author)


def test_events_on_closed_loop_are_ignored(client: TestClient) -> None:
    events = CollabEvents(
        ConnectionManager(), LockManager(), client.app.state.access
    )
    loop = asyncio.new_event_loop()
    loop.close()
    events.attach(loop)
    events.changed(1, "paragraphs", UUID(int=1))


class FakeWebSocket:
    def __init__(self, fail: bool = False) -> None:
        self.closed_with: list[int] = []
        self.fail = fail

    async def close(self, code: int) -> None:
        if self.fail:
            raise RuntimeError("уже закрито")
        self.closed_with.append(code)


def test_close_quietly_closes_only_once() -> None:
    websocket = FakeWebSocket()
    connection = Connection(websocket, UUID(int=1), "Олена", Role.EDITOR)
    asyncio.run(close_quietly(connection, 4403))
    asyncio.run(close_quietly(connection, 4408))
    assert websocket.closed_with == [4403]


def test_close_quietly_survives_failed_close() -> None:
    connection = Connection(
        FakeWebSocket(fail=True), UUID(int=1), "Олена", Role.GUEST
    )
    asyncio.run(close_quietly(connection, 4404))
    assert connection.closed


# File was created by Claude, verified by Kozynska Anastasia
