"""Роль Шлюзу: автентифікація запитів (інтерфейс I-02: Шлюз → IAM).

За архітектурою Шлюз перевіряє лише *автентичність* токена і передає
далі ідентифікованого користувача. Чи має користувач право на
конкретний документ, Шлюз не вирішує (high-level-design, 3.1).

У FastAPI цю роль виконує *залежність* (dependency). Маршрут, який
оголошує ``user: UserView = Depends(require_user)``, автоматично стає
захищеним, а в OpenAPI з'являється схема безпеки ``HTTPBearer``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NoReturn

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.iam import IamModule, UserView
from src.iam.application.audit import security_log
from src.iam.domain.errors import InvalidSessionError

# auto_error=False: без цього FastAPI сам повертав би 403 англійською
# при відсутньому заголовку. Нам потрібні 401 і український текст.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Токен сесії, отриманий під час входу або реєстрації.",
)

UNAUTHENTICATED_DETAIL = "Потрібна автентифікація."


@dataclass(frozen=True)
class AuthContext:
    """Автентифікований користувач разом із токеном його сесії."""

    user: UserView
    token: str = field(repr=False)


def get_iam(request: Request) -> IamModule:
    """Повертає модуль IAM, створений у ``create_app``."""
    return request.app.state.iam


def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    iam: IamModule = Depends(get_iam),
) -> AuthContext:
    """Вимагає дійсний Bearer-токен.

    Raises:
        HTTPException: 401 з заголовком ``WWW-Authenticate: Bearer``
            (так вимагає RFC 6750), якщо токен відсутній або недійсний.
    """
    if credentials is None:
        _reject(request, "missing_token")
    try:
        user = iam.verify_session(credentials.credentials)
    except InvalidSessionError:
        _reject(request, "invalid_token")
    return AuthContext(user=user, token=credentials.credentials)


def require_user(context: AuthContext = Depends(require_auth)) -> UserView:
    """Скорочення для маршрутів, яким потрібен лише користувач."""
    return context.user


def _reject(request: Request, reason: str) -> NoReturn:
    client = request.client.host if request.client else "unknown"
    # Проєктна вимога 4.5: спроби неавторизованого доступу логуються.
    security_log.warning(
        "unauthenticated_request reason=%s ip=%s path=%s",
        reason,
        client,
        request.url.path,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=UNAUTHENTICATED_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


# File was created by Claude (AI-assisted); review by a team member pending.
