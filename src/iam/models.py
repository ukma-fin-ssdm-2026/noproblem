"""Бізнес-правила IAM: політики та сутності.

1. **Політики** — числа з вимог (8 символів, 5 спроб, 15 хвилин) в
   одному місці, а не розкидані по коду як «магічні числа».
2. **Сутності** — дані разом із правилами, які до них стосуються
   (``user.is_locked(now)``, ``session.is_expired(...)``).

Усі класи незмінні (``frozen=True``). Метод, що «змінює» об'єкт,
повертає *нову* копію, тож стан у сховищі змінюється лише тоді, коли
сервіс явно збереже цю копію.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import ClassVar
from uuid import UUID

from src.iam.errors import (
    InvalidAccessRequestTransitionError,
    InvalidEmailError,
    InvalidNameError,
    PasswordTooLongError,
    PasswordTooShortError,
)

#
# Політики
#


@dataclass(frozen=True)
class PasswordPolicy:
    """Вимоги до пароля.

    Attributes:
        min_length: Мінімальна довжина (FR-001: 8 символів).
        max_length: Максимальна довжина. Обмежує роботу хеш-функції на
            один запит, щоб довгі паролі не стали вектором DoS.
    """

    min_length: int = 8
    max_length: int = 128

    def __post_init__(self) -> None:
        if not 1 <= self.min_length <= self.max_length:
            raise ValueError("Потрібно 1 <= min_length <= max_length.")

    def check(self, password: str) -> None:
        """Перевіряє пароль на відповідність політиці.

        Склад пароля (цифри, великі літери) свідомо не перевіряється:
        NIST SP 800-63B радить вимагати довжину, а не «складність».

        Raises:
            PasswordTooShortError: Пароль коротший за ``min_length``.
            PasswordTooLongError: Пароль довший за ``max_length``.
        """
        if len(password) < self.min_length:
            raise PasswordTooShortError(self.min_length)
        if len(password) > self.max_length:
            raise PasswordTooLongError(self.max_length)


@dataclass(frozen=True)
class LockoutPolicy:
    """Правила тимчасового блокування входу (FR-005, NFR-SEC-003).

    Attributes:
        max_failed_attempts: Скільки невдалих спроб поспіль дозволено.
        lock_duration: Тривалість блокування.
    """

    max_failed_attempts: int = 5
    lock_duration: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if self.max_failed_attempts < 1:
            raise ValueError("max_failed_attempts має бути >= 1.")
        if self.lock_duration <= timedelta(0):
            raise ValueError("lock_duration має бути додатною.")


@dataclass(frozen=True)
class SessionPolicy:
    """Строки життя сесії.

    Два незалежні таймаути — рекомендація OWASP: сесія закінчується
    після періоду бездіяльності або після абсолютного строку,
    залежно від того, що настане раніше.

    Attributes:
        idle_timeout: Скільки сесія живе без жодного запиту.
        absolute_lifetime: Максимальний строк сесії від моменту входу.
        touch_interval: Як часто оновлювати «останню активність».
            Без цього кожен запит означав би запис у сховище.
    """

    idle_timeout: timedelta = timedelta(minutes=30)
    absolute_lifetime: timedelta = timedelta(hours=12)
    touch_interval: timedelta = timedelta(minutes=1)

    def __post_init__(self) -> None:
        if self.idle_timeout <= timedelta(0):
            raise ValueError("idle_timeout має бути додатним.")
        if self.absolute_lifetime < self.idle_timeout:
            raise ValueError("absolute_lifetime має бути >= idle_timeout.")
        if not timedelta(0) <= self.touch_interval < self.idle_timeout:
            raise ValueError("touch_interval має бути менше idle_timeout.")


#
# Сутності
#


@dataclass(frozen=True)
class Email:
    """Нормалізована email-адреса.

    Нормалізація (обрізання пробілів і нижній регістр) потрібна, щоб
    ``Anna@Mail.com`` і ``anna@mail.com`` вважалися одним акаунтом
    (A-002: email унікальний).
    """

    value: str
    MAX_LENGTH: ClassVar[int] = 254  # обмеження RFC 5321

    @classmethod
    def parse(cls, raw: str) -> Email:
        """Перевіряє та нормалізує рядок, введений користувачем.

        Перевірка свідомо базова: існування адреси однаково
        підтверджує лише лист. Регулярний вираз не використовується,
        щоб уникнути ризику ReDoS.

        Raises:
            InvalidEmailError: Рядок не схожий на email-адресу.
        """
        value = raw.strip().lower()
        if not 3 <= len(value) <= cls.MAX_LENGTH:
            raise InvalidEmailError(value)
        local, separator, domain = value.partition("@")
        if (
            not separator
            or not local
            or "@" in domain
            or any(char.isspace() for char in value)
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
            or ".." in domain
        ):
            raise InvalidEmailError(value)
        return cls(value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DisplayName:
    """Ім'я користувача, яке бачать співредактори (FR-001, FR-025)."""

    value: str
    MAX_LENGTH: ClassVar[int] = 100

    @classmethod
    def parse(cls, raw: str) -> DisplayName:
        """Обрізає пробіли та перевіряє довжину імені.

        Raises:
            InvalidNameError: Ім'я порожнє або довше за ``MAX_LENGTH``.
        """
        value = raw.strip()
        if not 1 <= len(value) <= cls.MAX_LENGTH:
            raise InvalidNameError(value)
        return cls(value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class User:
    """Обліковий запис користувача.

    ``password_hash`` позначено ``repr=False``: якщо об'єкт випадково
    потрапить у журнал, хеш не розкриється.
    """

    id: UUID
    email: Email
    name: DisplayName
    password_hash: str = field(repr=False)
    created_at: datetime
    failed_login_attempts: int = 0
    locked_until: datetime | None = None

    def is_locked(self, now: datetime) -> bool:
        """Чи заблоковано вхід у момент ``now`` (FR-005)."""
        return self.locked_until is not None and now < self.locked_until

    def with_failed_login(self, now: datetime, policy: LockoutPolicy) -> User:
        """Повертає копію з урахованою невдалою спробою входу.

        Після ``policy.max_failed_attempts`` спроб поспіль вхід
        блокується на ``policy.lock_duration``, а лічильник
        скидається, щоб після блокування знову було 5 спроб.
        """
        attempts = self.failed_login_attempts + 1
        if attempts >= policy.max_failed_attempts:
            return replace(
                self,
                failed_login_attempts=0,
                locked_until=now + policy.lock_duration,
            )
        return replace(self, failed_login_attempts=attempts)

    def with_lock_cleared(self) -> User:
        """Повертає копію без лічильника спроб і без блокування."""
        return replace(self, failed_login_attempts=0, locked_until=None)

    def with_password_hash(self, password_hash: str) -> User:
        """Повертає копію з новим хешем пароля."""
        return replace(self, password_hash=password_hash)


@dataclass(frozen=True)
class Session:
    """Сесія автентифікованого користувача.

    Сам токен ніде не зберігається, лише його SHA-256 відбиток
    (``token_hash``). Якщо сховище скомпрометують, діючих токенів з
    нього отримати не можна.
    """

    id: UUID
    user_id: UUID
    token_hash: str = field(repr=False)
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime, policy: SessionPolicy) -> bool:
        """Чи закінчилася сесія (абсолютний строк або бездіяльність)."""
        return (
            now >= self.expires_at
            or now - self.last_seen_at >= policy.idle_timeout
        )

    def needs_touch(self, now: datetime, policy: SessionPolicy) -> bool:
        """Чи час оновити позначку останньої активності."""
        return now - self.last_seen_at >= policy.touch_interval

    def touched(self, now: datetime) -> Session:
        """Повертає копію з оновленою позначкою активності."""
        return replace(self, last_seen_at=now)


@dataclass(frozen=True)
class UnlockToken:
    """Одноразовий токен з листа для розблокування акаунта (FR-005)."""

    token_hash: str = field(repr=False)
    user_id: UUID
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        """Чи минув строк дії посилання."""
        return now >= self.expires_at


# Доступ до документів (FR-040–FR-043, FR-057)


class Role(str, Enum):
    """Роль користувача в конкретному документі."""

    OWNER = "owner"
    EDITOR = "editor"
    GUEST = "guest"


class Action(str, Enum):
    """Дія з документом, на яку потрібен дозвіл."""

    VIEW = "view"  # читати документ і абзаци
    EDIT = "edit"  # змінювати абзаци, перейменовувати (FR-014)
    TRASH = "trash"  # видаляти в кошик і відновлювати (FR-019, FR-022)
    MANAGE_ACCESS = "manage_access"  # ділитися, змінювати ролі (FR-057)


# Уся політика доступу — в одній таблиці. Чого тут немає, те заборонено
# (default deny): нова дія автоматично недоступна, доки її сюди не
# додадуть.
ROLE_PERMISSIONS: dict[Role, frozenset[Action]] = {
    Role.OWNER: frozenset(Action),
    Role.EDITOR: frozenset({Action.VIEW, Action.EDIT}),
    Role.GUEST: frozenset({Action.VIEW}),
}


@dataclass(frozen=True)
class DocumentAccess:
    """Запис «користувач має роль у документі» (сутність DocumentAccess).

    Власник документа — теж такий запис, з роллю ``OWNER``. Тому IAM
    лишається єдиним джерелом правди про ролі.
    """

    document_id: int
    user_id: UUID
    role: Role

    def allows(self, action: Action) -> bool:
        """Чи дозволяє роль цю дію."""
        return action in ROLE_PERMISSIONS[self.role]


class AccessRequestType(str, Enum):
    """Тип запиту на зміну доступу."""

    ACCESS = "access"
    ROLE = "role"


class AccessRequestStatus(str, Enum):
    """Статус розгляду запиту."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AccessRequest:
    """Запит користувача на доступ або майбутню зміну ролі."""

    id: UUID
    document_id: int
    requester_id: UUID
    request_type: AccessRequestType
    status: AccessRequestStatus
    created_at: datetime
    requested_role: Role | None = None
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.document_id <= 0:
            raise ValueError("document_id має бути додатним.")
        if self.request_type is AccessRequestType.ACCESS:
            if self.requested_role is not None:
                raise ValueError("Запит доступу не має requested_role.")
        elif self.requested_role is not Role.EDITOR:
            raise ValueError("Запит зміни ролі має запитувати роль Editor.")
        if (self.status is AccessRequestStatus.PENDING) != (
            self.resolved_at is None
        ):
            raise ValueError("Час розгляду має відповідати статусу запиту.")

    def decide(
        self, status: AccessRequestStatus, now: datetime
    ) -> AccessRequest:
        """Переводить очікуваний запит у підтверджений або відхилений."""
        if (
            self.status is not AccessRequestStatus.PENDING
            or status is AccessRequestStatus.PENDING
        ):
            raise InvalidAccessRequestTransitionError()
        return replace(self, status=status, resolved_at=now)


# File was created by Claude. Reviewed by Kozynska Anastasia
