"""Адаптери: конкретні реалізації портів з ``ports.py``.

Тут і тільки тут IAM торкається зовнішнього світу: словників у
пам'яті, бібліотеки ``argon2-cffi``, системного годинника, модуля
``secrets``, журналу. ``AuthService`` про ці класи не знає; з'єднує
їх ``bootstrap.py``.

Сховища в пам'яті — тимчасові: дані зникають після перезапуску, як і в
``src/api/main.py``. PostgreSQL-адаптер реалізує ті самі методи, і
``AuthService`` не зміниться.
"""

from __future__ import annotations

import logging
import secrets
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from src.iam.errors import (
    AccessDeniedError,
    AccessRequestAlreadyPendingError,
    AccessRequestNotFoundError,
    EmailAlreadyRegisteredError,
)
from src.iam.models import (
    AccessRequest,
    AccessRequestStatus,
    AccessRequestType,
    DocumentAccess,
    Email,
    Role,
    Session,
    UnlockToken,
    User,
)
from src.iam.ports import EmailMessage

# Сховища в пам'яті
#
# FastAPI виконує синхронні (``def``) обробники в пулі потоків, тож
# кілька запитів можуть одночасно звертатися до словників. Кожна
# операція виконується під ``threading.Lock`` — це відповідник
# транзакцій і обмежень UNIQUE у справжній БД.


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


#
# Хешування паролів
#


class Argon2PasswordHasher:
    """Реалізує ``PasswordHasher`` через Argon2id (``argon2-cffi``).

    Чому Argon2id: перший вибір OWASP Password Storage Cheat Sheet;
    алгоритм навмисно повільний і вимагає багато пам'яті, тому перебір
    на GPU дорогий. bcrypt теж прийнятний, але обрізає пароль до 72
    байтів. Криптографію не пишуть самостійно, тому використано
    перевірену бібліотеку (ліцензія MIT, активно підтримується).

    Параметри за замовчуванням — профіль RFC 9106 «low memory» (t=3,
    m=64 MiB, p=4). Для швидких тестів їх можна зменшити.
    """

    def __init__(
        self,
        time_cost: int | None = None,
        memory_cost: int | None = None,
        parallelism: int | None = None,
    ) -> None:
        overrides = {
            name: value
            for name, value in (
                ("time_cost", time_cost),
                ("memory_cost", memory_cost),
                ("parallelism", parallelism),
            )
            if value is not None
        }
        self._hasher = _Argon2(**overrides)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            # Неправильний пароль або пошкоджений хеш — однаково «не
            # пустити» (принцип fail securely), а не помилка 500.
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True


#
# Системні ресурси: час і випадковість
#


class SystemClock:
    """Реалізує ``Clock``: реальний час в UTC.

    Час завжди з часовим поясом: порівняння такого часу з часом без
    поясу Python забороняє (``TypeError``), тож UTC скрізь захищає від
    тонких помилок.
    """

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SecretsTokenGenerator:
    """Реалізує ``TokenGenerator`` через модуль ``secrets``.

    ``secrets`` бере випадковість з ОС (CSPRNG). Модуль ``random``
    тут не підходить, бо він передбачуваний (Bandit B311). 32 байти =
    256 біт, у base64url — 43 символи.
    """

    def __init__(self, num_bytes: int = 32) -> None:
        if num_bytes < 16:
            raise ValueError("Токен має містити щонайменше 128 біт.")
        self._num_bytes = num_bytes

    def new_token(self) -> str:
        return secrets.token_urlsafe(self._num_bytes)


#
# Пошта (I-19)
#

email_logger = logging.getLogger("notely.email")


class LoggingEmailSender:
    """Реалізує ``EmailSender``: «надсилає» лист у журнал застосунку.

    ЛИШЕ ДЛЯ РОЗРОБКИ. Тіло листа містить одноразове посилання, а
    секрети в журналі робочого середовища неприпустимі. ``bootstrap``
    вмикає цей адаптер лише без SMTP і попереджає про це. SMTP-адаптер
    (``smtplib`` + STARTTLS, порт 587) буде додано разом із PostgreSQL.
    """

    def send(self, message: EmailMessage) -> None:
        # WARNING, а не INFO: лист фактично НЕ надіслано. До того ж
        # рівень INFO не видно в консолі uvicorn без налаштування.
        email_logger.warning(
            "DEV EMAIL (лист не надіслано, SMTP не налаштовано) "
        )


class InMemoryAccessRepository:
    """Реалізує ``AccessRepository``; ключ — пара (документ, користувач)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[tuple[int, UUID], DocumentAccess] = {}
        self._requests: dict[UUID, AccessRequest] = {}

    def get(self, document_id: int, user_id: UUID) -> DocumentAccess | None:
        with self._lock:
            return self._by_key.get((document_id, user_id))

    def save(self, access: DocumentAccess) -> None:
        with self._lock:
            self._by_key[(access.document_id, access.user_id)] = access

    def ensure(self, access: DocumentAccess) -> DocumentAccess:
        with self._lock:
            key = (access.document_id, access.user_id)
            return self._by_key.setdefault(key, access)

    def delete(self, document_id: int, user_id: UUID) -> None:
        with self._lock:
            self._by_key.pop((document_id, user_id), None)

    def list_for_document(self, document_id: int) -> list[DocumentAccess]:
        with self._lock:
            return sorted(
                (
                    access
                    for access in self._by_key.values()
                    if access.document_id == document_id
                ),
                key=lambda access: access.user_id,
            )

    def list_for_user(self, user_id: UUID) -> list[DocumentAccess]:
        with self._lock:
            return sorted(
                (
                    access
                    for access in self._by_key.values()
                    if access.user_id == user_id
                ),
                key=lambda access: access.document_id,
            )

    def create_request(self, request: AccessRequest) -> AccessRequest:
        with self._lock:
            if any(
                existing.document_id == request.document_id
                and existing.requester_id == request.requester_id
                and existing.request_type is request.request_type
                and existing.status is AccessRequestStatus.PENDING
                for existing in self._requests.values()
            ):
                raise AccessRequestAlreadyPendingError()
            self._requests[request.id] = request
            return request

    def get_request(
        self, document_id: int, request_id: UUID
    ) -> AccessRequest | None:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request.document_id != document_id:
                return None
            return request

    def list_pending_requests(self, document_id: int) -> list[AccessRequest]:
        with self._lock:
            return sorted(
                (
                    request
                    for request in self._requests.values()
                    if request.document_id == document_id
                    and request.status is AccessRequestStatus.PENDING
                ),
                key=lambda request: (request.created_at, request.id),
            )

    def list_requests_for_user(
        self, user_id: UUID, document_id: int
    ) -> list[AccessRequest]:
        with self._lock:
            return sorted(
                (
                    request
                    for request in self._requests.values()
                    if request.requester_id == user_id
                    and request.document_id == document_id
                ),
                key=lambda request: (request.created_at, request.id),
                reverse=True,
            )

    def resolve_request(
        self,
        document_id: int,
        request_id: UUID,
        reviewer_id: UUID,
        status: AccessRequestStatus,
        now: datetime,
    ) -> AccessRequest:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request.document_id != document_id:
                raise AccessRequestNotFoundError()
            reviewer_access = self._by_key.get((document_id, reviewer_id))
            if (
                reviewer_access is None
                or reviewer_access.role is not Role.OWNER
            ):
                raise AccessDeniedError()
            resolved = request.decide(status, now)
            if status is AccessRequestStatus.APPROVED:
                role = request.requested_role or Role.GUEST
                key = (document_id, request.requester_id)
                if request.request_type is AccessRequestType.ROLE:
                    self._by_key[key] = DocumentAccess(
                        document_id, request.requester_id, role
                    )
                else:
                    self._by_key.setdefault(
                        key,
                        DocumentAccess(
                            document_id, request.requester_id, role
                        ),
                    )
            self._requests[request_id] = resolved
            return resolved


# File was created by Claude. Reviewed by Kozynska Anastasia
