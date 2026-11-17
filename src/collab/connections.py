"""Кімнати документів: хто зараз відкрив документ і розсилка повідомлень.

Усі методи викликаються з одного event loop, тож блокування не потрібне:
між ``await`` стан змінює лише одна корутина.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class Connection:
    """Одне WebSocket-з'єднання (одна вкладка) користувача з документом."""

    websocket: WebSocket = field(repr=False)
    user_id: UUID
    name: str


class ConnectionManager:
    """Кімната на кожен документ і лічильник вкладок користувача."""

    def __init__(self) -> None:
        self._rooms: dict[int, list[Connection]] = {}

    def connect(self, document_id: int, connection: Connection) -> bool:
        """Додає з'єднання; ``True``, якщо це перша вкладка користувача."""
        room = self._rooms.setdefault(document_id, [])
        first = not self._has_user(room, connection.user_id)
        room.append(connection)
        return first

    def disconnect(self, document_id: int, connection: Connection) -> bool:
        """Прибирає з'єднання; ``True``, якщо це була остання вкладка."""
        room = self._rooms.get(document_id, [])
        if connection in room:
            room.remove(connection)
        if not room:
            self._rooms.pop(document_id, None)
        return not self._has_user(room, connection.user_id)

    def users(self, document_id: int) -> list[dict[str, str]]:
        """Хто зараз у документі, кожен користувач один раз."""
        seen: dict[UUID, str] = {}
        for connection in self._rooms.get(document_id, []):
            seen.setdefault(connection.user_id, connection.name)
        return [
            {"user_id": str(user_id), "name": name}
            for user_id, name in seen.items()
        ]

    async def broadcast(
        self,
        document_id: int,
        message: dict[str, Any],
        *,
        exclude: Connection | None = None,
    ) -> None:
        """Надсилає повідомлення всім у кімнаті, крім ``exclude``."""
        for connection in list(self._rooms.get(document_id, [])):
            if connection is not exclude:
                await send(connection.websocket, message)

    @staticmethod
    def _has_user(room: list[Connection], user_id: UUID) -> bool:
        return any(c.user_id == user_id for c in room)


async def send(websocket: WebSocket, message: dict[str, Any]) -> None:
    """Надсилає JSON, не падаючи, якщо клієнт уже відключився.

    Таке з'єднання прибере його власний цикл читання, коли отримає
    ``websocket.disconnect``.
    """
    try:
        await websocket.send_json(message)
    except Exception:  # розсилка не має падати через одного клієнта
        logger.debug("collab_send_failed", exc_info=True)


# File was created by Claude, verified by Kozynska Anastasia
