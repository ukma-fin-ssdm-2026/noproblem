"""Порти: інтерфейси, через які IAM спілкується із зовнішнім світом.

Це серце архітектури «порти й адаптери» (гексагональної). Сценарії
використання (use cases) залежать лише від цих протоколів, а не від
конкретних класів. Тому:

* in-memory сховище можна замінити на PostgreSQL, не змінивши жодного
  рядка в ``application/`` чи ``domain/``;
* у тестах замість справжнього годинника, пошти й Argon2 можна
  підставити швидкі передбачувані підробки (fakes).

``typing.Protocol`` — це структурна типізація: клас підходить, якщо в
нього є потрібні методи, і успадковувати порт для цього не потрібно.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.iam.domain.models import Email, Session, UnlockToken, User


class UserRepository(Protocol):
    """Сховище облікових записів (інтерфейс I-15)."""

    def add(self, user: User) -> None:
        """Додає нового користувача.

        Перевірка унікальності email має бути *атомарною* всередині
        сховища (у PostgreSQL це обмеження UNIQUE). Перевірка
        «прочитати, чи існує → вставити» у коді сценарію не захищає від
        двох одночасних реєстрацій.

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

        Сценарій передає *чисту функцію* «старий стан → новий стан», а
        сховище гарантує, що між читанням і записом ніхто інший цього
        користувача не змінить. Без цього два паралельні невдалі входи
        могли б обидва прочитати ``failed_login_attempts == 4`` і
        записати 5 замість 6, і зловмисник отримав би зайві спроби
        (NFR-SEC-003). У PostgreSQL це ``SELECT ... FOR UPDATE`` у
        транзакції, у пам'яті це ``threading.Lock``.

        Якщо ``change`` кидає виняток, зміна не зберігається, а виняток
        передається викликачу.

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
        """Атомарно знаходить і видаляє токен.

        Атомарність гарантує одноразовість: два одночасні переходи за
        тим самим посиланням не можуть обидва бути успішними.
        """
        ...


class PasswordHasher(Protocol):
    """Повільне хешування паролів із сіллю (наприклад, Argon2id)."""

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

    Час іде через порт, а не через виклик ``datetime.now()`` усередині
    сценарію. Так тест «через 15 хвилин блокування знімається» займає
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

    Адаптер мусить кинути цей виняток, а не мовчки «проковтнути»
    помилку (I-19: збій пошти не можна маскувати під успішне
    надсилання).
    """


class EmailSender(Protocol):
    """Відправлення листів через зовнішній сервіс (інтерфейс I-19)."""

    def send(self, message: EmailMessage) -> None:
        """Надсилає лист.

        Raises:
            EmailDeliveryError: Лист не вдалося передати сервісу.
        """
        ...


# File was created by Claude (AI-assisted); review by a team member pending.
