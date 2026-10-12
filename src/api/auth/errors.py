"""Перетворення доменних винятків IAM на HTTP-відповіді.

Єдине місце, де вирішується, який статус і який текст отримає клієнт.
Таблиця явна: новий виняток без запису в ній стане 500 (і буде
помічений тестами), а не мовчки отримає випадковий код.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.api.common import ApiError
from src.iam import errors as iam_errors

INVALID_CREDENTIALS_DETAIL = "Невірний email або пароль"
ACCOUNT_LOCKED_DETAIL = (
    "Вхід тимчасово заблоковано через кілька невдалих спроб. "
    "Спробуйте пізніше або скористайтеся посиланням з листа."
)

# Порядок важливий: шукається перший клас, від якого успадкований
# виняток, тому конкретніші класи стоять вище за загальніші.
_ERROR_TABLE: tuple[tuple[type[iam_errors.IamError], int, str], ...] = (
    (
        iam_errors.PasswordTooShortError,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Пароль має містити щонайменше 8 символів.",
    ),
    (
        iam_errors.PasswordTooLongError,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Пароль має містити не більше ніж 128 символів.",
    ),
    (
        iam_errors.InvalidEmailError,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Некоректний формат email.",
    ),
    (
        iam_errors.InvalidNameError,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Ім'я має містити від 1 до 100 символів.",
    ),
    (
        iam_errors.EmailAlreadyRegisteredError,
        status.HTTP_409_CONFLICT,
        "Користувач із таким email уже зареєстрований.",
    ),
    (
        iam_errors.InvalidCredentialsError,
        status.HTTP_401_UNAUTHORIZED,
        INVALID_CREDENTIALS_DETAIL,
    ),
    (
        iam_errors.AccountLockedError,
        status.HTTP_423_LOCKED,
        ACCOUNT_LOCKED_DETAIL,
    ),
    (
        iam_errors.InvalidSessionError,
        status.HTTP_401_UNAUTHORIZED,
        "Потрібна автентифікація.",
    ),
    (
        iam_errors.InvalidUnlockTokenError,
        status.HTTP_400_BAD_REQUEST,
        "Посилання для розблокування недійсне або застаріле.",
    ),
)


def iam_error_to_response(exc: iam_errors.IamError) -> JSONResponse:
    """Будує HTTP-відповідь для доменного винятку IAM.

    Args:
        exc: Виняток, що вилетів зі сценарію IAM.

    Returns:
        JSON-відповідь у форматі ``ApiError``.

    Raises:
        IamError: Якщо для типу винятку немає запису в таблиці. Тоді
            виняток передається далі й стає 500. Краще явна помилка,
            ніж неправильний код відповіді.
    """
    for error_type, status_code, detail in _ERROR_TABLE:
        if isinstance(exc, error_type):
            return JSONResponse(
                status_code=status_code,
                content=ApiError(detail=detail).model_dump(),
                headers=_extra_headers(exc),
            )
    raise exc


def _extra_headers(exc: iam_errors.IamError) -> dict[str, str] | None:
    if isinstance(exc, iam_errors.AccountLockedError):
        return {"Retry-After": str(exc.retry_after_seconds)}
    if isinstance(
        exc,
        (iam_errors.InvalidCredentialsError, iam_errors.InvalidSessionError),
    ):
        return {"WWW-Authenticate": "Bearer"}
    return None


def register_iam_error_handlers(app: FastAPI) -> None:
    """Підключає обробник доменних винятків IAM до застосунку."""

    async def handle_iam_error(
        _request: Request, exc: iam_errors.IamError
    ) -> JSONResponse:
        return iam_error_to_response(exc)

    app.add_exception_handler(iam_errors.IamError, handle_iam_error)


# File was created by Claude. Reviewed by Kozynska Anastasia
