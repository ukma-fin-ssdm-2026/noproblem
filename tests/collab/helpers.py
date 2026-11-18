"""Хелпери для WebSocket-тестів Collab.

Звичайні функції, а не фікстури: їх викликають із параметрами (хто, який
документ, яка роль), тож тест читається як сценарій.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.api.helpers import API

Headers = dict[str, str]


def ws_url(document_id: int) -> str:
    return f"{API}/collab/documents/{document_id}"


def token(who: Headers) -> str:
    return who["Authorization"].removeprefix("Bearer ")


def share(
    client: TestClient,
    owner: Headers,
    document_id: int,
    email: str,
    role: str,
) -> None:
    response = client.put(
        f"{API}/documents/{document_id}/access",
        json={"email": email, "role": role},
        headers=owner,
    )
    assert response.status_code == 200


@contextmanager
def joined(client: TestClient, document_id: int, who: Headers) -> Iterator:
    """Відкритий і автентифікований WebSocket; ``welcome`` уже прочитано."""
    with client.websocket_connect(ws_url(document_id)) as ws:
        ws.send_json({"type": "auth", "token": token(who)})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        ws.welcome = welcome
        yield ws


def close_code(ws: Any) -> int:
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    return closed.value.code


def user_id(client: TestClient, who: Headers) -> str:
    return client.get(f"{API}/auth/me", headers=who).json()["id"]


def assert_quiet(ws: Any) -> None:
    """Перевіряє, що для з'єднання більше нічого не надіслано.

    Надсилає ``ping``: якщо наступне повідомлення — ``pong``, отже, нічого
    іншого в черзі не було.
    """
    ws.send_json({"type": "ping"})
    assert ws.receive_json() == {"type": "pong"}


# File was created by Claude, verified by Kozynska Anastasia
