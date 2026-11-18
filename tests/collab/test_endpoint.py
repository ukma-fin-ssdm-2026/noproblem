"""WebSocket-ендпоінт спільного редагування.

Протокол: docs/architecture/collab-protocol.md.

Фікстури (клієнт, користувачі, документ) — у ``tests/collab/conftest.py``,
хелпери — у ``tests/collab/helpers.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.collab import endpoint
from tests.api.helpers import API
from tests.collab.helpers import (
    Headers,
    close_code,
    joined,
    share,
    token,
    user_id,
    ws_url,
)

# -- Авторизація -----------------------------------------------------------


def test_invalid_token_closes_with_4401(
    client: TestClient, document_id: int
) -> None:
    with client.websocket_connect(ws_url(document_id)) as ws:
        ws.send_json({"type": "auth", "token": "не-токен"})
        assert close_code(ws) == 4401


@pytest.mark.parametrize(
    "first",
    [{"type": "ping"}, {"type": "auth"}, {"type": "auth", "token": 42}],
    ids=["not-auth", "no-token", "token-not-string"],
)
def test_first_message_must_be_auth(
    client: TestClient, document_id: int, first: dict
) -> None:
    with client.websocket_connect(ws_url(document_id)) as ws:
        ws.send_json(first)
        assert close_code(ws) == 4401


def test_first_message_not_json_closes_with_4401(
    client: TestClient, document_id: int
) -> None:
    with client.websocket_connect(ws_url(document_id)) as ws:
        ws.send_text("{не json")
        assert close_code(ws) == 4401


def test_no_auth_in_time_closes_with_4401(
    client: TestClient, document_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(endpoint, "AUTH_TIMEOUT_S", 0.1)
    with client.websocket_connect(ws_url(document_id)) as ws:
        assert close_code(ws) == 4401


def test_foreign_document_closes_with_4403(
    client: TestClient, document_id: int, petro: Headers
) -> None:
    with client.websocket_connect(ws_url(document_id)) as ws:
        ws.send_json({"type": "auth", "token": token(petro)})
        assert close_code(ws) == 4403


def test_unknown_document_closes_with_4403(
    client: TestClient, olena: Headers
) -> None:
    """Як і в REST: не видаємо, що документа не існує."""
    with client.websocket_connect(ws_url(999)) as ws:
        ws.send_json({"type": "auth", "token": token(olena)})
        assert close_code(ws) == 4403


def test_trashed_document_closes_with_4404(
    client: TestClient, olena: Headers, document_id: int
) -> None:
    response = client.delete(f"{API}/documents/{document_id}", headers=olena)
    assert response.status_code == 204
    with client.websocket_connect(ws_url(document_id)) as ws:
        ws.send_json({"type": "auth", "token": token(olena)})
        assert close_code(ws) == 4404


def test_disconnect_before_auth_leaves_no_trace(
    client: TestClient, document_id: int
) -> None:
    with client.websocket_connect(ws_url(document_id)):
        pass
    assert client.app.state.connections.users(document_id) == []


# -- welcome і присутність -------------------------------------------------


def test_welcome_describes_document_state(
    client: TestClient, olena: Headers, document_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        me = user_id(client, olena)
        assert ws.welcome == {
            "type": "welcome",
            "user_id": me,
            "role": "owner",
            "users": [{"user_id": me, "name": "Олена"}],
            "locks": {},
        }


@pytest.mark.parametrize("role", ["editor", "guest"])
def test_welcome_reports_member_role(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    role: str,
) -> None:
    share(client, olena, document_id, "petro@example.com", role)
    with joined(client, document_id, petro) as ws:
        assert ws.welcome["role"] == role


def test_second_user_sees_presence_joined_and_left(
    client: TestClient, olena: Headers, petro: Headers, document_id: int
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    with joined(client, document_id, olena) as ws_olena:
        with joined(client, document_id, petro) as ws_petro:
            assert len(ws_petro.welcome["users"]) == 2
            assert ws_olena.receive_json() == {
                "type": "presence",
                "user_id": user_id(client, petro),
                "name": "Петро",
                "status": "joined",
            }
        left = ws_olena.receive_json()
        assert (left["type"], left["status"]) == ("presence", "left")


# -- Повідомлення ----------------------------------------------------------


def test_ping_gets_pong(
    client: TestClient, olena: Headers, document_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


@pytest.mark.parametrize(
    "raw",
    [
        "{не json",
        "[1, 2]",
        '{"type": "unknown"}',
        '{"type": "lock.acquire"}',
        '{"type": "lock.acquire", "paragraph_id": "1"}',
        '{"type": "lock.acquire", "paragraph_id": true}',
        '{"type": "lock.release", "paragraph_id": 0}',
        '{"type": "paragraph.edit", "paragraph_id": 1}',
    ],
)
def test_invalid_message_gets_error_and_keeps_connection(
    client: TestClient, olena: Headers, document_id: int, raw: str
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_text(raw)
        error = ws.receive_json()
        assert (error["type"], error["code"]) == ("error", "invalid_message")
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_binary_message_gets_invalid_message(
    client: TestClient, olena: Headers, document_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_bytes(b"\x00\x01")
        error = ws.receive_json()
        assert (error["type"], error["code"]) == ("error", "invalid_message")


# -- Блокування ------------------------------------------------------------


def test_acquire_grants_lock_and_notifies_everyone(
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
            ws_olena.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            changed = {
                "type": "lock.changed",
                "paragraph_id": paragraph_id,
                "user_id": user_id(client, olena),
            }
            assert ws_olena.receive_json() == {
                "type": "lock.granted",
                "paragraph_id": paragraph_id,
            }
            assert ws_olena.receive_json() == changed
            assert ws_petro.receive_json() == changed


def test_repeated_acquire_is_granted_without_new_broadcast(
    client: TestClient, olena: Headers, document_id: int, paragraph_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        acquire = {"type": "lock.acquire", "paragraph_id": paragraph_id}
        ws.send_json(acquire)
        ws.receive_json()  # lock.granted
        ws.receive_json()  # lock.changed
        ws.send_json(acquire)
        assert ws.receive_json()["type"] == "lock.granted"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_locked_paragraph_is_denied_to_other_editor(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    olena_id = client.app.state.iam.verify_session(token(olena)).id
    client.app.state.lock_manager.acquire(document_id, paragraph_id, olena_id)
    with joined(client, document_id, petro) as ws:
        assert ws.welcome["locks"] == {
            str(paragraph_id): user_id(client, olena)
        }
        ws.send_json({"type": "lock.acquire", "paragraph_id": paragraph_id})
        assert ws.receive_json() == {
            "type": "lock.denied",
            "paragraph_id": paragraph_id,
            "holder": user_id(client, olena),
            "reason": "locked",
        }


def test_guest_cannot_lock(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "guest")
    with joined(client, document_id, petro) as ws:
        ws.send_json({"type": "lock.acquire", "paragraph_id": paragraph_id})
        assert ws.receive_json() == {
            "type": "lock.denied",
            "paragraph_id": paragraph_id,
            "holder": None,
            "reason": "forbidden",
        }


def test_revoked_member_is_disconnected_on_acquire(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    with joined(client, document_id, petro) as ws:
        revoked = client.delete(
            f"{API}/documents/{document_id}/access/"
            f"{user_id(client, petro)}",
            headers=olena,
        )
        assert revoked.status_code in (200, 204)
        ws.send_json({"type": "lock.acquire", "paragraph_id": paragraph_id})
        assert close_code(ws) == 4403


def test_release_frees_paragraph(
    client: TestClient, olena: Headers, document_id: int, paragraph_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_json({"type": "lock.acquire", "paragraph_id": paragraph_id})
        ws.receive_json()  # lock.granted
        ws.receive_json()  # lock.changed
        ws.send_json({"type": "lock.release", "paragraph_id": paragraph_id})
        assert ws.receive_json() == {
            "type": "lock.changed",
            "paragraph_id": paragraph_id,
            "user_id": None,
        }
    assert client.app.state.lock_manager.locks(document_id) == {}


def test_release_of_foreign_lock_does_nothing(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    manager = client.app.state.lock_manager
    olena_id = client.app.state.iam.verify_session(token(olena)).id
    manager.acquire(document_id, paragraph_id, olena_id)
    with joined(client, document_id, petro) as ws:
        ws.send_json({"type": "lock.release", "paragraph_id": paragraph_id})
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
    assert manager.holder(document_id, paragraph_id) == olena_id


# -- Розсилка змін ---------------------------------------------------------


def test_edit_from_lock_holder_reaches_others_only(
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
            ws_olena.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            ws_olena.receive_json()  # lock.granted
            ws_olena.receive_json()  # lock.changed
            ws_petro.receive_json()  # lock.changed

            ws_olena.send_json(
                {
                    "type": "paragraph.edit",
                    "paragraph_id": paragraph_id,
                    "content": "Новий текст",
                }
            )
            assert ws_petro.receive_json() == {
                "type": "paragraph.updated",
                "paragraph_id": paragraph_id,
                "content": "Новий текст",
                "author_id": user_id(client, olena),
            }
            # Автор свою зміну назад не отримує: наступне — pong.
            ws_olena.send_json({"type": "ping"})
            assert ws_olena.receive_json() == {"type": "pong"}


def test_edit_without_lock_is_rejected(
    client: TestClient, olena: Headers, document_id: int, paragraph_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_json(
            {
                "type": "paragraph.edit",
                "paragraph_id": paragraph_id,
                "content": "Х",
            }
        )
        error = ws.receive_json()
        assert (error["type"], error["code"]) == ("error", "lock_required")


def test_too_long_edit_is_rejected(
    client: TestClient, olena: Headers, document_id: int, paragraph_id: int
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_json({"type": "lock.acquire", "paragraph_id": paragraph_id})
        ws.receive_json()  # lock.granted
        ws.receive_json()  # lock.changed
        ws.send_json(
            {
                "type": "paragraph.edit",
                "paragraph_id": paragraph_id,
                "content": "x" * (endpoint.MAX_PARAGRAPH_LENGTH + 1),
            }
        )
        error = ws.receive_json()
        assert (error["type"], error["code"]) == ("error", "too_long")


# -- Курсори ---------------------------------------------------------------


def test_cursor_reaches_others_but_not_author(
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
            ws_olena.send_json(
                {"type": "cursor", "paragraph_id": paragraph_id, "offset": 3}
            )
            assert ws_petro.receive_json() == {
                "type": "cursor",
                "user_id": user_id(client, olena),
                "paragraph_id": paragraph_id,
                "offset": 3,
            }
            # Автор свій курсор назад не отримує: наступне — pong.
            ws_olena.send_json({"type": "ping"})
            assert ws_olena.receive_json() == {"type": "pong"}


def test_cursor_without_paragraph_means_focus_left(
    client: TestClient, olena: Headers, petro: Headers, document_id: int
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    with joined(client, document_id, olena) as ws_olena:
        with joined(client, document_id, petro) as ws_petro:
            ws_olena.receive_json()  # presence: joined
            ws_petro.send_json(
                {"type": "cursor", "paragraph_id": None, "offset": 0}
            )
            message = ws_olena.receive_json()
            assert (message["type"], message["paragraph_id"]) == (
                "cursor",
                None,
            )


def test_guest_cursor_is_forbidden(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "guest")
    with joined(client, document_id, petro) as ws:
        ws.send_json(
            {"type": "cursor", "paragraph_id": paragraph_id, "offset": 0}
        )
        error = ws.receive_json()
        assert (error["type"], error["code"]) == ("error", "forbidden")
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


@pytest.mark.parametrize(
    "fields",
    [
        {"paragraph_id": 1},
        {"paragraph_id": 1, "offset": -1},
        {"paragraph_id": 1, "offset": endpoint.MAX_PARAGRAPH_LENGTH + 1},
        {"paragraph_id": 1, "offset": "5"},
        {"paragraph_id": 1, "offset": True},
        {"paragraph_id": "1", "offset": 0},
        {"paragraph_id": 0, "offset": 0},
        {"paragraph_id": True, "offset": 0},
    ],
)
def test_invalid_cursor_gets_invalid_message(
    client: TestClient, olena: Headers, document_id: int, fields: dict
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_json({"type": "cursor", **fields})
        error = ws.receive_json()
        assert (error["type"], error["code"]) == ("error", "invalid_message")


# -- Відключення -----------------------------------------------------------


def test_disconnect_releases_locks_and_notifies(
    client: TestClient,
    olena: Headers,
    petro: Headers,
    document_id: int,
    paragraph_id: int,
) -> None:
    share(client, olena, document_id, "petro@example.com", "editor")
    with joined(client, document_id, petro) as ws_petro:
        with joined(client, document_id, olena) as ws_olena:
            ws_petro.receive_json()  # presence: joined
            ws_olena.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            ws_olena.receive_json()  # lock.granted
            ws_petro.receive_json()  # lock.changed
        assert ws_petro.receive_json() == {
            "type": "lock.changed",
            "paragraph_id": paragraph_id,
            "user_id": None,
        }
        left = ws_petro.receive_json()
        assert (left["type"], left["status"]) == ("presence", "left")


def test_second_tab_keeps_locks_until_last_tab_closes(
    client: TestClient, olena: Headers, document_id: int, paragraph_id: int
) -> None:
    manager = client.app.state.lock_manager
    with joined(client, document_id, olena):
        with joined(client, document_id, olena) as tab:
            assert len(tab.welcome["users"]) == 1
            tab.send_json(
                {"type": "lock.acquire", "paragraph_id": paragraph_id}
            )
            tab.receive_json()  # lock.granted
        # Друга вкладка закрита, але перша ще відкрита: блокування живе.
        assert manager.holder(document_id, paragraph_id) is not None
    assert manager.locks(document_id) == {}


def test_silence_closes_with_4408_and_releases_locks(
    client: TestClient,
    olena: Headers,
    document_id: int,
    paragraph_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with joined(client, document_id, olena) as ws:
        ws.send_json({"type": "lock.acquire", "paragraph_id": paragraph_id})
        ws.receive_json()  # lock.granted
        ws.receive_json()  # lock.changed
        monkeypatch.setattr(endpoint, "HEARTBEAT_TIMEOUT_S", 0.1)
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        assert close_code(ws) == 4408
    assert client.app.state.lock_manager.locks(document_id) == {}


# File was created by Claude, verified by Kozynska Anastasia
