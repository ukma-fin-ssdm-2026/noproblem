"""Винятки модуля IAM.

Винятки описують, *що* пішло не так з погляду бізнес-правил, але не
*як* це показати користувачу. Перетворення на HTTP-статус і текст
повідомлення виконує адаптер (``src/api/auth/errors.py``). Тому той
самий виняток можна буде відобразити і в REST, і в WebSocket-сесії
модуля Collab, не змінюючи IAM.
"""

from __future__ import annotations

import math
from datetime import datetime


class IamError(Exception):
    """Базовий клас усіх помилок модуля IAM."""


class InvalidEmailError(IamError):
    """Email має некоректний формат (FR-001)."""


class InvalidNameError(IamError):
    """Ім'я порожнє або задовге (FR-001)."""


class InvalidPasswordError(IamError):
    """Пароль не відповідає політиці паролів (FR-001, FR-002)."""


class PasswordTooShortError(InvalidPasswordError):
    """Пароль коротший за мінімальну довжину (FR-002)."""

    def __init__(self, min_length: int) -> None:
        super().__init__(f"password shorter than {min_length}")
        self.min_length = min_length


class PasswordTooLongError(InvalidPasswordError):
    """Пароль довший за максимальну довжину (захист від DoS)."""

    def __init__(self, max_length: int) -> None:
        super().__init__(f"password longer than {max_length}")
        self.max_length = max_length


class EmailAlreadyRegisteredError(IamError):
    """Акаунт з таким email уже існує (FR-002)."""


class InvalidCredentialsError(IamError):
    """Невірна пара email/пароль.

    Навмисно не уточнює, яке саме поле неправильне (FR-004).
    """


class AccountLockedError(IamError):
    """Вхід тимчасово заблоковано після серії невдалих спроб (FR-005).

    Attributes:
        locked_until: Момент (UTC), після якого вхід знову можливий.
        retry_after_seconds: Скільки секунд лишилося до кінця блокування
            (щонайменше 1). Обчислюється в момент відмови, щоб адаптер
            не звертався до системного годинника сам.
    """

    def __init__(self, locked_until: datetime, now: datetime) -> None:
        super().__init__(f"account locked until {locked_until.isoformat()}")
        self.locked_until = locked_until
        remaining = (locked_until - now).total_seconds()
        self.retry_after_seconds = max(1, math.ceil(remaining))


class InvalidSessionError(IamError):
    """Токен сесії відсутній, невідомий, відкликаний або прострочений."""


class InvalidUnlockTokenError(IamError):
    """Посилання розблокування невідоме, вже використане або застаріле."""


# File was created by Claude. Reviewed by Kozynska Anastasia
