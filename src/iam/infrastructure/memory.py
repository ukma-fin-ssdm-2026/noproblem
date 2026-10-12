"""Сховища IAM у пам'яті процесу.

Тимчасова реалізація портів зі ``src/iam/application/ports.py``: дані
зникають після перезапуску, як і в наявному ``src/api/main.py``.
PostgreSQL-адаптер (частина 3) реалізує ті самі методи, і решта коду
не зміниться.

Потокобезпечність. FastAPI виконує синхронні (``def``) обробники в
пулі потоків, тож кілька запитів можуть одночасно звертатися до
словників. Кожна операція виконується під ``threading.Lock``. Це
відповідник транзакцій та обмежень UNIQUE у справжній БД.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from uuid import UUID

from src.iam.domain.errors import EmailAlreadyRegisteredError
from src.iam.domain.models import Email, Session, UnlockToken, User


class InMemoryUserRepository:
    """Реалізує ``UserRepository`` на словниках."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[UUID, User] = {}
        self._id_by_email: dict[Email, UUID] = {}

    def add(self, user: User) -> None:
        with self._lock:
            if user.email in self._id_by_email:
                raise EmailAlreadyRegisteredError(str(user.email))
            self._by_id[user.id] = user
            self._id_by_email[user.email] = user.id

    def get_by_id(self, user_id: UUID) -> User | None:
        with self._lock:
            return self._by_id.get(user_id)

    def get_by_email(self, email: Email) -> User | None:
        with self._lock:
            user_id = self._id_by_email.get(email)
            return None if user_id is None else self._by_id[user_id]

    def update(
        self, user_id: UUID, change: Callable[[User], User]
    ) -> User | None:
        with self._lock:
            current = self._by_id.get(user_id)
            if current is None:
                return None
            updated = change(current)  # виняток тут → нічого не записано
            if updated.id != current.id or updated.email != current.email:
                raise ValueError("update не може змінювати id або email.")
            self._by_id[user_id] = updated
            return updated


class InMemorySessionRepository:
    """Реалізує ``SessionRepository``; ключ — відбиток токена."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_token_hash: dict[str, Session] = {}

    def add(self, session: Session) -> None:
        with self._lock:
            self._by_token_hash[session.token_hash] = session

    def get_by_token_hash(self, token_hash: str) -> Session | None:
        with self._lock:
            return self._by_token_hash.get(token_hash)

    def save(self, session: Session) -> None:
        with self._lock:
            # Не «воскрешаємо» сесію, яку тим часом видалив вихід.
            if session.token_hash in self._by_token_hash:
                self._by_token_hash[session.token_hash] = session

    def delete(self, session_id: UUID) -> None:
        with self._lock:
            for token_hash, session in list(self._by_token_hash.items()):
                if session.id == session_id:
                    del self._by_token_hash[token_hash]

    def delete_by_token_hash(self, token_hash: str) -> bool:
        with self._lock:
            return self._by_token_hash.pop(token_hash, None) is not None


class InMemoryUnlockTokenRepository:
    """Реалізує ``UnlockTokenRepository``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_hash: dict[str, UnlockToken] = {}

    def add(self, token: UnlockToken) -> None:
        with self._lock:
            self._by_hash[token.token_hash] = token

    def pop(self, token_hash: str) -> UnlockToken | None:
        with self._lock:
            return self._by_hash.pop(token_hash, None)


# File was created by Claude (AI-assisted); review by a team member pending.
