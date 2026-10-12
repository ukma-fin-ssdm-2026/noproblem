"""Об'єкти, які IAM повертає назовні (Data Transfer Objects).

Сутність ``User`` назовні не віддається, бо вона містить хеш пароля і
лічильники блокування. Адаптери (REST, WebSocket) та інші модулі
бачать лише ``UserView``. Так поля, які не можна розкривати, не
потраплять у відповідь API навіть випадково.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.iam.domain.models import User


@dataclass(frozen=True)
class UserView:
    """Публічні дані автентифікованого користувача."""

    id: UUID
    email: str
    name: str
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> UserView:
        """Створює представлення з доменної сутності."""
        return cls(
            id=user.id,
            email=str(user.email),
            name=str(user.name),
            created_at=user.created_at,
        )


@dataclass(frozen=True)
class IssuedSession:
    """Щойно видана сесія.

    Відкритий ``access_token`` існує лише тут, щоб передати його
    клієнту один раз. ``repr=False`` не дає йому потрапити в лог.

    Attributes:
        access_token: Токен для заголовка ``Authorization: Bearer``.
        expires_at: Абсолютний кінець сесії. Через бездіяльність вона
            може закінчитися раніше.
    """

    access_token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class AuthResult:
    """Результат успішної реєстрації або входу."""

    user: UserView
    session: IssuedSession


# File was created by Claude (AI-assisted); review by a team member pending.
