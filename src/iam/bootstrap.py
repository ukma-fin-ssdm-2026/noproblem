"""Збирання модуля IAM з конкретних адаптерів.

Єдине місце, де ``AuthService`` з'єднується з реалізаціями портів.
Тести передають свої адаптери через аргументи ``build_iam`` (наприклад,
підроблений годинник), а решта коду про це не знає.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from src.iam.access import AccessService
from src.iam.adapters import (
    Argon2PasswordHasher,
    InMemoryAccessRepository,
    InMemorySessionRepository,
    InMemoryUnlockTokenRepository,
    InMemoryUserRepository,
    LoggingEmailSender,
    SecretsTokenGenerator,
    SystemClock,
)
from src.iam.models import LockoutPolicy, PasswordPolicy, SessionPolicy
from src.iam.ports import Clock, EmailSender, PasswordHasher, TokenGenerator
from src.iam.service import AuthService

logger = logging.getLogger(__name__)

DEFAULT_UNLOCK_PAGE_URL = "http://localhost:3000/unlock"


@dataclass(frozen=True)
class IamSettings:
    """Налаштування модуля IAM.

    Attributes:
        unlock_page_url: Сторінка вебклієнта, на яку веде посилання
            розблокування з листа.
        password_policy: Вимоги до пароля.
        lockout_policy: Правила блокування входу.
        session_policy: Строки життя сесії.
    """

    unlock_page_url: str = DEFAULT_UNLOCK_PAGE_URL
    password_policy: PasswordPolicy = field(default_factory=PasswordPolicy)
    lockout_policy: LockoutPolicy = field(default_factory=LockoutPolicy)
    session_policy: SessionPolicy = field(default_factory=SessionPolicy)

    @classmethod
    def from_env(cls) -> IamSettings:
        """Читає налаштування зі змінних оточення.

        Підтримується ``NOTELY_UNLOCK_PAGE_URL``. Політики безпеки
        беруться з вимог і через оточення не змінюються, щоб
        помилкова конфігурація не могла, наприклад, вимкнути
        блокування.
        """
        return cls(
            unlock_page_url=os.getenv(
                "NOTELY_UNLOCK_PAGE_URL", DEFAULT_UNLOCK_PAGE_URL
            )
        )


def build_iam(
    settings: IamSettings | None = None,
    *,
    clock: Clock | None = None,
    password_hasher: PasswordHasher | None = None,
    email_sender: EmailSender | None = None,
    token_generator: TokenGenerator | None = None,
) -> AuthService:
    """Створює готовий до роботи ``AuthService``.

    Args:
        settings: Налаштування; за замовчуванням ``IamSettings()``.
        clock: Годинник; за замовчуванням системний.
        password_hasher: Хешування; за замовчуванням Argon2id.
        email_sender: Пошта; за замовчуванням журнал (лише розробка).
        token_generator: Генератор токенів; за замовчуванням ``secrets``.
    """
    settings = settings or IamSettings()
    if email_sender is None:
        logger.warning(
            "SMTP не налаштовано: листи IAM пишуться в журнал. "
            "Використовуйте це лише для розробки."
        )
        email_sender = LoggingEmailSender()

    return AuthService(
        users=InMemoryUserRepository(),
        sessions=InMemorySessionRepository(),
        unlock_tokens=InMemoryUnlockTokenRepository(),
        hasher=password_hasher or Argon2PasswordHasher(),
        tokens=token_generator or SecretsTokenGenerator(),
        email_sender=email_sender,
        clock=clock or SystemClock(),
        password_policy=settings.password_policy,
        lockout_policy=settings.lockout_policy,
        session_policy=settings.session_policy,
        unlock_page_url=settings.unlock_page_url,
    )


def build_access(auth: AuthService) -> AccessService:
    """Створює ``AccessService``, що шукає користувачів через ``auth``."""
    return AccessService(access=InMemoryAccessRepository(), auth=auth)


# File was created by Claude. Reviewed by Kozynska Anastasia
