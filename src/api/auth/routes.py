"""Маршрути ``/api/v1/auth``: тонкий HTTP-адаптер до модуля IAM (I-05).

Кожен обробник робить три речі: бере дані з HTTP-запиту, викликає
один метод ``AuthService`` і перетворює результат на HTTP-відповідь.

Чому обробники ``def``, а не ``async def``. Хешування Argon2 займає
десятки мілісекунд процесорного часу. Синхронний обробник FastAPI
виконує в пулі потоків, і цикл подій лишається вільним для інших
запитів. У ``async def`` той самий виклик заблокував би весь сервер
на час хешування.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.auth.errors import (
    ACCOUNT_LOCKED_DETAIL,
    INVALID_CREDENTIALS_DETAIL,
)
from src.api.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UnlockRequest,
    UserResponse,
)
from src.api.common import (
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    error_response,
)
from src.api.security import AuthContext, get_iam, require_auth, require_user
from src.iam import AuthService, UserView

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Зареєструватися",
    description=(
        "Створює обліковий запис і одразу відкриває сесію (FR-001, "
        "FR-002, US-003). Email нормалізується до нижнього регістру."
    ),
    response_description="Новий користувач і токен сесії.",
    responses={
        status.HTTP_201_CREATED: {"description": "Акаунт створено."},
        status.HTTP_409_CONFLICT: error_response(
            "Email уже використовується.",
            "Користувач із таким email уже зареєстрований.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: error_response(
            "Некоректний email, ім'я або пароль коротший за 8 символів.",
            "Пароль має містити щонайменше 8 символів.",
        ),
    },
)
def register(
    payload: RegisterRequest,
    iam: AuthService = Depends(get_iam),
) -> AuthResponse:
    result = iam.register(payload.email, payload.name, payload.password)
    return AuthResponse.from_result(result)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Увійти",
    description=(
        "Перевіряє email і пароль та створює сесію (FR-003). Помилка "
        "не уточнює, яке поле неправильне (FR-004). Після 5 невдалих "
        "спроб поспіль вхід блокується на 15 хвилин, а на email "
        "надсилається посилання для розблокування (FR-005)."
    ),
    response_description="Користувач і токен нової сесії.",
    responses={
        status.HTTP_200_OK: {"description": "Вхід виконано."},
        status.HTTP_401_UNAUTHORIZED: error_response(
            "Невірна пара email/пароль.", INVALID_CREDENTIALS_DETAIL
        ),
        status.HTTP_423_LOCKED: {
            **error_response(
                "Вхід тимчасово заблоковано. Заголовок Retry-After містить "
                "кількість секунд до розблокування.",
                ACCOUNT_LOCKED_DETAIL,
            ),
            "headers": {
                "Retry-After": {
                    "description": "Секунд до автоматичного розблокування.",
                    "schema": {"type": "integer"},
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def login(
    payload: LoginRequest,
    iam: AuthService = Depends(get_iam),
) -> AuthResponse:
    result = iam.login(payload.email, payload.password)
    return AuthResponse.from_result(result)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Вийти",
    description=(
        "Завершує поточну сесію на сервері: токен стає недійсним "
        "одразу (FR-006)."
    ),
    response_description="Сесію завершено; відповідь не містить тіла.",
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Сесію завершено."},
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
    },
)
def logout(
    context: AuthContext = Depends(require_auth),
    iam: AuthService = Depends(get_iam),
) -> None:
    iam.logout(context.token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Поточний користувач",
    description="Повертає дані власника токена сесії.",
    response_description="Автентифікований користувач.",
    responses={
        status.HTTP_200_OK: {"description": "Користувача визначено."},
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
    },
)
def read_current_user(
    user: UserView = Depends(require_user),
) -> UserResponse:
    return UserResponse.from_view(user)


@router.post(
    "/unlock",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Розблокувати акаунт за посиланням з листа",
    description=(
        "Знімає тимчасове блокування входу за одноразовим токеном із "
        "листа (FR-005). Публічний маршрут: токен сам підтверджує право "
        "на дію."
    ),
    response_description="Акаунт розблоковано.",
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Акаунт розблоковано."},
        status.HTTP_400_BAD_REQUEST: error_response(
            "Токен невідомий, уже використаний або застарілий.",
            "Посилання для розблокування недійсне або застаріле.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def unlock(
    payload: UnlockRequest,
    iam: AuthService = Depends(get_iam),
) -> None:
    iam.unlock_account(payload.token)


# File was created by Claude. Reviewed by Kozynska Anastasia
