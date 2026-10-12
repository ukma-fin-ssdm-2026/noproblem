"""Pydantic-схеми запитів і відповідей маршрутів ``/auth``.

Схеми відповідають лише за *форму* даних (тип, максимальна довжина).
Бізнес-правила (мінімум 8 символів, формат email) перевіряє домен
IAM, бо:

* FR-002 вимагає конкретного повідомлення («пароль закороткий»), а
  загальний обробник валідації цього проєкту повертає лише
  «Некоректні вхідні дані.»;
* правило в домені діє для будь-якого викликача, не лише для REST.

Максимальні довжини дублюють доменні навмисно: це перший рубіж
захисту від надвеликих тіл запитів (defense in depth).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.iam import AuthResult, UserView


class RegisterRequest(BaseModel):
    """Дані для реєстрації."""

    email: str = Field(
        max_length=254,
        description="Email користувача; має бути унікальним.",
        examples=["olena@example.com"],
    )
    name: str = Field(
        max_length=100,
        description="Ім'я, яке бачитимуть співредактори (1–100 символів).",
        examples=["Олена"],
    )
    password: str = Field(
        max_length=128,
        description="Пароль: від 8 до 128 символів.",
        examples=["correct-horse-battery"],
    )


class LoginRequest(BaseModel):
    """Дані для входу."""

    email: str = Field(max_length=254, examples=["olena@example.com"])
    password: str = Field(max_length=128, examples=["correct-horse-battery"])


class UnlockRequest(BaseModel):
    """Токен із посилання в листі розблокування."""

    token: str = Field(
        min_length=1,
        max_length=256,
        description="Значення параметра token з посилання в листі.",
    )


class UserResponse(BaseModel):
    """Публічні дані користувача."""

    id: UUID = Field(description="Ідентифікатор користувача.")
    email: str = Field(description="Нормалізований email (нижній регістр).")
    name: str = Field(description="Ім'я користувача.")
    created_at: datetime = Field(description="Час реєстрації в UTC.")

    @classmethod
    def from_view(cls, user: UserView) -> UserResponse:
        """Перетворює DTO модуля IAM на HTTP-відповідь."""
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
        )


class AuthResponse(BaseModel):
    """Результат реєстрації або входу."""

    access_token: str = Field(
        description=(
            "Токен сесії. Передавайте його в заголовку "
            "Authorization: Bearer <токен>."
        )
    )
    token_type: Literal["bearer"] = Field(
        default="bearer", description="Тип токена (RFC 6750)."
    )
    expires_at: datetime = Field(
        description=(
            "Абсолютний кінець сесії в UTC. Після 30 хвилин бездіяльності "
            "сесія завершується раніше."
        )
    )
    user: UserResponse = Field(description="Автентифікований користувач.")

    @classmethod
    def from_result(cls, result: AuthResult) -> AuthResponse:
        """Перетворює результат сценарію на HTTP-відповідь."""
        return cls(
            access_token=result.session.access_token,
            expires_at=result.session.expires_at,
            user=UserResponse.from_view(result.user),
        )


# File was created by Claude. Reviewed by Kozynska Anastasia
