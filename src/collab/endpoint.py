"""WebSocket-ендпоінт спільного редагування (ADR-001, ADR-003).

Протокол описано в ``docs/architecture/collab-protocol.md``.

Ендпоінт лише тримає блокування і розсилає зміни. Текст абзаців
зберігає фронтенд через REST, тож у базу дані потрапляють одним шляхом.
Синхронні сервіси (IAM, документи) викликаються через
``asyncio.to_thread``, щоб не блокувати event loop.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.documents import MAX_PARAGRAPH_LENGTH
from src.collab.connections import (
    Connection,
    ConnectionManager,
    close_quietly,
    send,
)
from src.collab.locks import LockManager
from src.documents.errors import DocumentNotFoundError
from src.iam import AccessService, Action, AuthService, Role, UserView
from src.iam.errors import AccessDeniedError, InvalidSessionError
from src.iam.service import security_log

router = APIRouter(prefix="/api/v1/collab", tags=["Collab"])

# Модульні змінні, а не константи в коді: тести зменшують їх через
# monkeypatch, щоб не чекати по 5 с.
AUTH_TIMEOUT_S = 5.0
HEARTBEAT_TIMEOUT_S = 5.0

CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_HEARTBEAT_TIMEOUT = 4408

ERROR_MESSAGES = {
    "invalid_message": "Некоректне повідомлення.",
    "lock_required": "Щоб змінити абзац, спершу візьміть його на редагування.",
    "too_long": (
        f"Абзац задовгий: щонайбільше {MAX_PARAGRAPH_LENGTH} символів."
    ),
    "forbidden": "Курсори доступні лише редакторам.",
}


class _Close(Exception):
    """Закрити з'єднання з кодом ``code`` (наприклад, доступ відкликано)."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class _Session:
    """Усе, що потрібно обробникам одного з'єднання."""

    websocket: WebSocket
    document_id: int
    user: UserView
    connection: Connection
    access: AccessService
    locks: LockManager
    connections: ConnectionManager

    @property
    def role(self) -> Role:
        return self.connection.role

    @property
    def can_edit(self) -> bool:
        return self.connection.can_edit

    async def reply(self, message: dict[str, Any]) -> None:
        await send(self.websocket, message)

    async def broadcast(
        self, message: dict[str, Any], *, include_self: bool = True
    ) -> None:
        await self.connections.broadcast(
            self.document_id,
            message,
            exclude=None if include_self else self.connection,
        )

    async def error(self, code: str) -> None:
        await self.reply(
            {"type": "error", "code": code, "message": ERROR_MESSAGES[code]}
        )


# -- Маршрут ---------------------------------------------------------------


@router.websocket("/documents/{document_id}")
async def collab_document(websocket: WebSocket, document_id: int) -> None:
    """Підключення до документа: auth → welcome → обмін повідомленнями."""
    await websocket.accept()
    authenticated = await _authenticate(websocket, document_id)
    if authenticated is None:
        return
    user, role = authenticated
    app_state = websocket.app.state
    session = _Session(
        websocket=websocket,
        document_id=document_id,
        user=user,
        connection=Connection(websocket, user.id, user.name, role),
        access=app_state.access,
        locks=app_state.lock_manager,
        connections=app_state.connections,
    )
    await _join(session)
    try:
        await _serve(session)
    finally:
        # Прибирання не можна обривати на півдорозі: інакше інші клієнти
        # не дізнаються, що абзаци звільнено.
        with anyio.CancelScope(shield=True):
            await _leave(session)


# -- Вхід і вихід ----------------------------------------------------------


async def _authenticate(
    websocket: WebSocket, document_id: int
) -> tuple[UserView, Role] | None:
    """Чекає ``auth``, перевіряє токен і доступ; інакше закриває."""
    try:
        first = await asyncio.wait_for(
            _receive_json(websocket), AUTH_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        return await _reject(websocket, "auth_timeout")
    except WebSocketDisconnect:
        return None

    token = first.get("token") if _is_auth(first) else None
    if not isinstance(token, str):
        return await _reject(websocket, "missing_token")

    iam: AuthService = websocket.app.state.iam
    try:
        user = await asyncio.to_thread(iam.verify_session, token)
    except InvalidSessionError:
        return await _reject(websocket, "invalid_token")

    documents = websocket.app.state.documents.service
    try:
        await asyncio.to_thread(documents.get, user.id, document_id)
    except AccessDeniedError:
        # AccessService.check уже записав відмову в журнал безпеки.
        await websocket.close(code=CLOSE_FORBIDDEN)
        return None
    except DocumentNotFoundError:
        await websocket.close(code=CLOSE_NOT_FOUND)
        return None

    access: AccessService = websocket.app.state.access
    role = await asyncio.to_thread(document_role, access, user.id, document_id)
    return user, role


def _is_auth(message: Any) -> bool:
    return isinstance(message, dict) and message.get("type") == "auth"


async def _reject(websocket: WebSocket, reason: str) -> None:
    client = websocket.client.host if websocket.client else "unknown"
    # Проєктна вимога 4.5: спроби неавторизованого доступу логуються.
    security_log.warning(
        "unauthenticated_websocket reason=%s ip=%s path=%s",
        reason,
        client,
        websocket.url.path,
    )
    await websocket.close(code=CLOSE_UNAUTHENTICATED)


def document_role(
    access: AccessService, user_id: UUID, document_id: int
) -> Role:
    """Роль користувача в документі (за умови, що VIEW у нього є)."""
    if access.has_permission(user_id, document_id, Action.MANAGE_ACCESS):
        return Role.OWNER
    if access.has_permission(user_id, document_id, Action.EDIT):
        return Role.EDITOR
    return Role.GUEST


async def _join(session: _Session) -> None:
    first_tab = session.connections.connect(
        session.document_id, session.connection
    )
    locks = session.locks.locks(session.document_id)
    await session.reply(
        {
            "type": "welcome",
            "user_id": str(session.user.id),
            "role": session.role.value,
            "users": session.connections.users(session.document_id),
            "locks": {str(pid): str(uid) for pid, uid in locks.items()},
        }
    )
    if first_tab:
        await session.broadcast(
            _presence(session, "joined"), include_self=False
        )


async def _leave(session: _Session) -> None:
    """Прибирає з'єднання; блокування знімає лише з останньою вкладкою."""
    last_tab = session.connections.disconnect(
        session.document_id, session.connection
    )
    if not last_tab:
        return
    released = session.locks.release_all(session.document_id, session.user.id)
    for paragraph_id in released:
        await session.broadcast(_lock_changed(paragraph_id, None))
    await session.broadcast(_presence(session, "left"))


# -- Цикл повідомлень ------------------------------------------------------


async def _serve(session: _Session) -> None:
    websocket = session.websocket
    while True:
        try:
            message = await asyncio.wait_for(
                _receive_json(websocket), HEARTBEAT_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            await close_quietly(session.connection, CLOSE_HEARTBEAT_TIMEOUT)
            return
        except WebSocketDisconnect:
            return

        kind = message.get("type") if isinstance(message, dict) else None
        handler = _HANDLERS.get(kind) if isinstance(kind, str) else None
        if handler is None:
            await session.error("invalid_message")
            continue
        try:
            await handler(session, message)
        except _Close as close:
            await close_quietly(session.connection, close.code)
            return


async def _receive_json(websocket: WebSocket) -> Any:
    """Наступне повідомлення як JSON; ``None``, якщо це не JSON-текст.

    Raises:
        WebSocketDisconnect: Клієнт закрив з'єднання.
    """
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    text = message.get("text")
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


# -- Обробники -------------------------------------------------------------


async def _on_ping(session: _Session, _message: dict[str, Any]) -> None:
    await session.reply({"type": "pong"})


async def _on_lock_acquire(session: _Session, message: dict[str, Any]) -> None:
    paragraph_id = _paragraph_id(message)
    if paragraph_id is None:
        await session.error("invalid_message")
        return

    # Роль могла змінитися після входу, тож перевіряємо щоразу.
    can_view, can_edit = await asyncio.to_thread(_permissions, session)
    if not can_view:
        raise _Close(CLOSE_FORBIDDEN)
    if not can_edit:
        await session.reply(_lock_denied(paragraph_id, None, "forbidden"))
        return

    locks, document_id, user_id = (
        session.locks,
        session.document_id,
        session.user.id,
    )
    already_mine = locks.holder(document_id, paragraph_id) == user_id
    if locks.acquire(document_id, paragraph_id, user_id):
        await session.reply(
            {"type": "lock.granted", "paragraph_id": paragraph_id}
        )
        if not already_mine:
            await session.broadcast(_lock_changed(paragraph_id, user_id))
    else:
        holder = locks.holder(document_id, paragraph_id)
        await session.reply(_lock_denied(paragraph_id, holder, "locked"))


async def _on_lock_release(session: _Session, message: dict[str, Any]) -> None:
    paragraph_id = _paragraph_id(message)
    if paragraph_id is None:
        await session.error("invalid_message")
        return
    if session.locks.release(
        session.document_id, paragraph_id, session.user.id
    ):
        await session.broadcast(_lock_changed(paragraph_id, None))


async def _on_paragraph_edit(
    session: _Session, message: dict[str, Any]
) -> None:
    paragraph_id = _paragraph_id(message)
    content = message.get("content")
    if paragraph_id is None or not isinstance(content, str):
        await session.error("invalid_message")
        return
    if len(content) > MAX_PARAGRAPH_LENGTH:
        await session.error("too_long")
        return
    holder = session.locks.holder(session.document_id, paragraph_id)
    if holder != session.user.id:
        await session.error("lock_required")
        return
    await session.broadcast(
        {
            "type": "paragraph.updated",
            "paragraph_id": paragraph_id,
            "content": content,
            "author_id": str(session.user.id),
        },
        include_self=False,
    )


async def _on_cursor(session: _Session, message: dict[str, Any]) -> None:
    raw_paragraph_id = message.get("paragraph_id")
    paragraph_id = _paragraph_id(message)
    offset = _offset(message)
    # paragraph_id: null — фокус пішов з тексту; це коректне значення.
    if offset is None or (
        paragraph_id is None and raw_paragraph_id is not None
    ):
        await session.error("invalid_message")
        return
    if not session.can_edit:
        await session.error("forbidden")
        return
    await session.broadcast(
        {
            "type": "cursor",
            "user_id": str(session.user.id),
            "paragraph_id": paragraph_id,
            "offset": offset,
        },
        include_self=False,
    )


_Handler = Callable[[_Session, dict[str, Any]], Awaitable[None]]

_HANDLERS: dict[str, _Handler] = {
    "ping": _on_ping,
    "lock.acquire": _on_lock_acquire,
    "lock.release": _on_lock_release,
    "paragraph.edit": _on_paragraph_edit,
    "cursor": _on_cursor,
}


# -- Допоміжне -------------------------------------------------------------


def _paragraph_id(message: dict[str, Any]) -> int | None:
    value = message.get("paragraph_id")
    # bool — підклас int, тож true/false відкидаємо окремо.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _offset(message: dict[str, Any]) -> int | None:
    value = message.get("offset")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 0 <= value <= MAX_PARAGRAPH_LENGTH:
        return None
    return value


def _permissions(session: _Session) -> tuple[bool, bool]:
    access, user_id, document_id = (
        session.access,
        session.user.id,
        session.document_id,
    )
    return (
        access.has_permission(user_id, document_id, Action.VIEW),
        access.has_permission(user_id, document_id, Action.EDIT),
    )


def _lock_changed(paragraph_id: int, user_id: UUID | None) -> dict[str, Any]:
    return {
        "type": "lock.changed",
        "paragraph_id": paragraph_id,
        "user_id": str(user_id) if user_id else None,
    }


def _lock_denied(
    paragraph_id: int, holder: UUID | None, reason: str
) -> dict[str, Any]:
    return {
        "type": "lock.denied",
        "paragraph_id": paragraph_id,
        "holder": str(holder) if holder else None,
        "reason": reason,
    }


def _presence(session: _Session, status: str) -> dict[str, Any]:
    return {
        "type": "presence",
        "user_id": str(session.user.id),
        "name": session.user.name,
        "status": status,
    }


# File was created by Claude, verified by Kozynska Anastasia
