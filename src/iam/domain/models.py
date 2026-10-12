"""Доменні сутності та об'єкти-значення модуля IAM.

Усі класи незмінні (``frozen=True``). Метод, що «змінює» сутність,
повертає *нову* копію. Так оновлення стають явними: стан у сховищі
змінюється лише тоді, коли репозиторій зберігає нову копію, і ніколи
мимохідь. Це той самий підхід ``model_copy(update=...)``, що
використано в ``src/api/main.py``.

Поля відповідають ER-моделі (``docs/architecture/data-model.md``).
Сутностей ``Session`` і ``UnlockToken`` у ній поки немає; потрібно
додати їх під час переходу на PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from src.iam.domain.errors import InvalidEmailError, InvalidNameError
from src.iam.domain.policies import LockoutPolicy, SessionPolicy


@dataclass(frozen=True)
class Email:
    """Нормалізована email-адреса.

    Нормалізація (обрізання пробілів і нижній регістр) потрібна, щоб
    ``Anna@Mail.com`` і ``anna@mail.com`` вважалися одним акаунтом
    (A-002: email унікальний). За RFC 5321 локальна частина формально
    чутлива до регістру, але жоден поширений поштовий сервіс цим не
    користується, тому так роблять практично всі застосунки.
    """

    value: str
    MAX_LENGTH: ClassVar[int] = 254  # обмеження RFC 5321 на шлях адреси

    @classmethod
    def parse(cls, raw: str) -> Email:
        """Перевіряє та нормалізує сирий рядок із запиту.

        Перевірка свідомо базова: повну відповідність RFC 5322 майже
        ніхто не реалізує, а існування адреси однаково підтверджує лише
        лист. Регулярний вираз не використовується, щоб уникнути ризику
        ReDoS.

        Args:
            raw: Рядок, введений користувачем.

        Returns:
            Нормалізований ``Email``.

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

    ``password_hash`` позначено ``repr=False``: якщо сутність випадково
    потрапить у лог або повідомлення про помилку, хеш не розкриється.
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
        """Фіксує невдалу спробу входу.

        Після ``policy.max_failed_attempts`` спроб поспіль вхід
        блокується на ``policy.lock_duration``, а лічильник скидається,
        щоб після завершення блокування користувач знову мав повний
        набір спроб.

        Args:
            now: Поточний час (UTC).
            policy: Правила блокування.

        Returns:
            Оновлена копія користувача.
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
        """Скидає лічильник невдалих спроб і блокування.

        Викликається після успішного входу та після переходу за
        посиланням розблокування.
        """
        return replace(self, failed_login_attempts=0, locked_until=None)

    def with_password_hash(self, password_hash: str) -> User:
        """Повертає копію з новим хешем (для оновлення параметрів хешу)."""
        return replace(self, password_hash=password_hash)


@dataclass(frozen=True)
class Session:
    """Сесія автентифікованого користувача.

    Сам токен ніде не зберігається, лише його SHA-256 відбиток
    (``token_hash``). Якщо базу даних скомпрометують, діючі токени
    з неї отримати неможливо.
    """

    id: UUID
    user_id: UUID
    token_hash: str = field(repr=False)
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime, policy: SessionPolicy) -> bool:
        """Чи закінчилася сесія через абсолютний строк або бездіяльність."""
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


# File was created by Claude (AI-assisted); review by a team member pending.
