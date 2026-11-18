"""Події модулів для Collab: зміни документа і зміни доступу (рішення 1).

``CollabEvents`` реалізує два порти: ``DocumentEvents`` (модуль
документів) і ``AccessEvents`` (IAM). Самі модулі про Collab не знають:
їм лише передають цей об'єкт у ``create_app``.

Порти викликаються з потоку REST (FastAPI виконує синхронні маршрути в
пулі потоків), а розсилка живе в event loop. Тому методи порту лише
ставлять задачу в loop через ``asyncio.run_coroutine_threadsafe`` і не
чекають результату: REST-запит не гальмує через WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any
from uuid import UUID

from src.collab.connections import ConnectionManager, close_quietly
from src.collab.endpoint import (
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    document_role,
)
from src.collab.locks import LockManager
from src.iam import AccessService, Action, Role

logger = logging.getLogger(__name__)


class CollabEvents:
    """Розсилає події модулів у WebSocket-кімнати документів."""

    def __init__(
        self,
        connections: ConnectionManager,
        locks: LockManager,
        access: AccessService,
    ) -> None:
        self._connections = connections
        self._locks = locks
        self._access = access
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        """Підключає event loop застосунку (викликається в ``lifespan``)."""
        self._loop = loop

    def detach(self) -> None:
        """Від'єднує loop при зупинці застосунку."""
        self._loop = None

    # -- DocumentEvents ---------------------------------------------------

    def changed(self, document_id: int, kind: str, author_id: UUID) -> None:
        """Документ змінено через REST (paragraphs / title / trashed)."""
        self._schedule(self._document_changed(document_id, kind, author_id))

    # -- AccessEvents -----------------------------------------------------

    def access_changed(self, document_id: int, user_id: UUID) -> None:
        """Роль користувача в документі змінено, надано або забрано."""
        self._schedule(self._access_changed(document_id, user_id))

    # -- Робота в event loop ----------------------------------------------

    async def _document_changed(
        self, document_id: int, kind: str, author_id: UUID
    ) -> None:
        if not self._connections.connections_of(document_id):
            return
        # Усім, включно з автором: REST не знає, з якої вкладки запит.
        await self._connections.broadcast(
            document_id,
            {
                "type": "document.changed",
                "kind": kind,
                "author_id": str(author_id),
            },
        )
        if kind == "trashed":
            for connection in self._connections.connections_of(document_id):
                await close_quietly(connection, CLOSE_NOT_FOUND)

    async def _access_changed(self, document_id: int, user_id: UUID) -> None:
        if not self._connections.connections_of(document_id, user_id):
            return
        role = await asyncio.to_thread(
            self._current_role, document_id, user_id
        )
        # Поки йшла перевірка, людина могла вийти: беремо список заново.
        connections = self._connections.connections_of(document_id, user_id)
        if role is None:
            # Блокування й presence: left зробить звичайний вихід (_leave),
            # коли цикл читання отримає закриття.
            for connection in connections:
                await close_quietly(connection, CLOSE_FORBIDDEN)
            return
        for connection in connections:
            connection.role = role
        if role not in (Role.OWNER, Role.EDITOR):
            for paragraph_id in self._locks.release_all(document_id, user_id):
                await self._connections.broadcast(
                    document_id,
                    {
                        "type": "lock.changed",
                        "paragraph_id": paragraph_id,
                        "user_id": None,
                    },
                )

    def _current_role(self, document_id: int, user_id: UUID) -> Role | None:
        """Роль користувача або ``None``, якщо доступу немає зовсім."""
        if not self._access.has_permission(user_id, document_id, Action.VIEW):
            return None
        return document_role(self._access, user_id, document_id)

    # -- Міст потоків -----------------------------------------------------

    def _schedule(self, coroutine: Coroutine[Any, Any, None]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            # Застосунок без lifespan (частина тестів) або вже зупинений.
            coroutine.close()
            return
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except RuntimeError:  # loop зупинився між перевіркою і викликом
            coroutine.close()
            return
        future.add_done_callback(_log_failure)


def _log_failure(future: Future[None]) -> None:
    if not future.cancelled() and future.exception() is not None:
        logger.error("collab_event_failed", exc_info=future.exception())


# File was created by Claude, verified by Kozynska Anastasia
