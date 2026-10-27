"""Порти: інтерфейси, через які IAM спілкується із зовнішнім світом.

Порт описує, *що* потрібно сервісу (наприклад, «знайти користувача за
email»), але не *як* це зроблено. Реалізації (адаптери) лежать в
``adapters.py`` і ``postgres.py``, а в тестах
у ``tests/fakes.py``. ``AuthService`` знає лише ці протоколи, тому
заміна сховища чи пошти не змінює в ньому жодного рядка.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.iam.models import (
    DocumentAccess,
    Email,
    Session,
    UnlockToken,
    User,
)


class UserRepository(Protocol):
    """Сховище облікових записів (інтерфейс I-15)."""

    def add(self, user: User) -> None:
        """Додає нового користувача.

        Унікальність email має перевірятися *атомарно* всередині
        сховища (у PostgreSQL це обмеження UNIQUE), щоб дві
        одночасні реєстрації не створили два акаунти.

        Raises:
            EmailAlreadyRegisteredError: Email уже зайнятий.
        """
        ...

    def get_by_id(self, user_id: UUID) -> User | None:
        """Повертає користувача за ідентифікатором або ``None``."""
        ...

    def get_by_email(self, email: Email) -> User | None:
        """Повертає користувача за нормалізованим email або ``None``."""
        ...

    def update(
        self, user_id: UUID, change: Callable[[User], User]
    ) -> User | None:
        """Атомарно застосовує ``change`` до актуального стану користувача.

        Сервіс передає функцію «старий стан → новий стан», а сховище
        гарантує, що між читанням і записом ніхто інший цього
        користувача не змінить. Інакше два паралельні невдалі входи
        могли б обидва прочитати «4 спроби» і записати «5», і
        зловмисник отримав би зайві спроби (NFR-SEC-003). У PostgreSQL
        це ``SELECT ... FOR UPDATE`` у транзакції.

        Якщо ``change`` кидає виняток, нічого не зберігається.

        Returns:
            Збережений новий стан або ``None``, якщо користувача немає.
        """
        ...


class SessionRepository(Protocol):
    """Сховище сесій (інтерфейс I-15)."""

    def add(self, session: Session) -> None:
        """Зберігає нову сесію."""
        ...

    def get_by_token_hash(self, token_hash: str) -> Session | None:
        """Шукає сесію за відбитком токена."""
        ...

    def save(self, session: Session) -> None:
        """Перезаписує наявну сесію (наприклад, нову позначку активності)."""
        ...

    def delete(self, session_id: UUID) -> None:
        """Видаляє сесію; якщо її вже немає, нічого не робить."""
        ...

    def delete_by_token_hash(self, token_hash: str) -> bool:
        """Видаляє сесію за відбитком токена.

        Returns:
            ``True``, якщо сесію було знайдено й видалено.
        """
        ...


class UnlockTokenRepository(Protocol):
    """Сховище одноразових токенів розблокування."""

    def add(self, token: UnlockToken) -> None:
        """Зберігає новий токен."""
        ...

    def pop(self, token_hash: str) -> UnlockToken | None:
        """Атомарно знаходить і видаляє токен (гарантія одноразовості)."""
        ...


class PasswordHasher(Protocol):
    """Повільне хешування паролів із сіллю (Argon2id)."""

    def hash(self, password: str) -> str:
        """Повертає рядок хешу разом із сіллю та параметрами алгоритму."""
        ...

    def verify(self, password_hash: str, password: str) -> bool:
        """Перевіряє пароль; ніколи не кидає виняток через неправильний."""
        ...

    def needs_rehash(self, password_hash: str) -> bool:
        """Чи створено хеш зі слабшими параметрами, ніж поточні."""
        ...


class TokenGenerator(Protocol):
    """Джерело криптографічно стійких випадкових токенів."""

    def new_token(self) -> str:
        """Повертає новий URL-безпечний токен."""
        ...


class Clock(Protocol):
    """Джерело поточного часу.

    Час іде через порт, а не через ``datetime.now()`` усередині
    сервісу. Тому тест «через 15 хвилин блокування знімається» займає
    мілісекунди: підроблений годинник просто «перемотується».
    """

    def now(self) -> datetime:
        """Поточний час із часовим поясом UTC."""
        ...


@dataclass(frozen=True)
class EmailMessage:
    """Лист, який IAM доручає надіслати (інтерфейс I-19)."""

    recipient: str
    subject: str
    body: str


class EmailDeliveryError(Exception):
    """Поштовий сервіс не прийняв лист.

    Адаптер мусить кинути цей виняток, а не «проковтнути» помилку
    (I-19: збій пошти не можна маскувати під успішне надсилання).
    """


class EmailSender(Protocol):
    """Відправлення листів через зовнішній сервіс (інтерфейс I-19)."""

    def send(self, message: EmailMessage) -> None:
        """Надсилає лист.

        Raises:
            EmailDeliveryError: Лист не вдалося передати сервісу.
        """
        ...


class AccessRepository(Protocol):
    """Сховище ролей у документах (таблиця DocumentAccess, I-15)."""

    def get(self, document_id: int, user_id: UUID) -> DocumentAccess | None:
        """Повертає роль користувача в документі або ``None``."""
        ...

    def save(self, access: DocumentAccess) -> None:
        """Додає запис або замінює роль, якщо запис уже є."""
        ...

    def ensure(self, access: DocumentAccess) -> DocumentAccess:
        """Додає роль лише за її відсутності та повертає збережений запис."""
        ...

    def delete(self, document_id: int, user_id: UUID) -> None:
        """Видаляє запис; якщо його немає, нічого не робить."""
        ...

    def list_for_document(self, document_id: int) -> list[DocumentAccess]:
        """Усі учасники документа."""
        ...

    def list_for_user(self, user_id: UUID) -> list[DocumentAccess]:
        """Усі документи, до яких користувач має доступ."""
        ...


# File was created by Claude. Reviewed and modified by Kozynska Anastasia
