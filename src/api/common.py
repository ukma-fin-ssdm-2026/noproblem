"""Спільні для всіх маршрутів моделі помилок і описи відповідей.

Винесено з ``main.py``, щоб маршрути IAM (``src/api/auth``) і
документів використовували один і той самий клас ``ApiError``. Без
цього в OpenAPI з'явилися б дві різні схеми з тим самим ім'ям, а
імпорт ``main.py`` з маршрутів IAM створив би циклічну залежність.
"""

from __future__ import annotations

from fastapi import status
from pydantic import BaseModel, Field


class ApiError(BaseModel):
    """Стандартна відповідь API з помилкою."""

    detail: str = Field(description="Коротке пояснення помилки.")


def error_response(description: str, example: str) -> dict:
    """Будує опис відповіді з помилкою для параметра ``responses=``.

    Args:
        description: Опис випадку для OpenAPI.
        example: Приклад тексту поля ``detail``.

    Returns:
        Словник у форматі, який очікує FastAPI.
    """
    return {
        "model": ApiError,
        "description": description,
        "content": {"application/json": {"example": {"detail": example}}},
    }


UNAUTHORIZED_RESPONSE = error_response(
    "Не автентифіковано: відсутній або недійсний токен.",
    "Потрібна автентифікація.",
)

AUTH_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
    status.HTTP_403_FORBIDDEN: error_response(
        "Недостатньо прав для виконання цієї дії.",
        "Недостатньо прав для цієї дії.",
    ),
}

VALIDATION_ERROR_RESPONSE = error_response(
    "Вхідні дані не пройшли валідацію.",
    "Некоректні вхідні дані.",
)


# File was created by Claude (AI-assisted); review by a team member pending.
