"""Composition root: збирання модуля IAM з конкретних адаптерів.

Тільки тут сценарії з'єднуються з реалізаціями портів. Тест чи інше
середовище передає власні адаптери через аргументи ``build_iam``
(наприклад, підроблений годинник), а решта коду про це не знає. Цей
прийом називається впровадженням залежностей (dependency injection)
без окремого фреймворку.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from src.iam.application.authentication.login import LoginUser
from src.iam.application.authentication.logout import LogoutUser
from src.iam.application.authentication.register import RegisterUser
from src.iam.application.authentication.sessions import SessionIssuer
from src.iam.application.authentication.unlock import (
    UnlockAccount,
    UnlockNotifier,
)
from src.iam.application.authentication.verify_session import VerifySession
from src.iam.application.ports import (
    Clock,
    EmailSender,
    PasswordHasher,
    TokenGenerator,
)
from src.iam.domain.policies import (
    LockoutPolicy,
    PasswordPolicy,
    SessionPolicy,
)
from src.iam.infrastructure.argon2_hasher import Argon2PasswordHasher
from src.iam.infrastructure.email import LoggingEmailSender
from src.iam.infrastructure.memory import (
    InMemorySessionRepository,
    InMemoryUnlockTokenRepository,
    InMemoryUserRepository,
)
from src.iam.infrastructure.system import SecretsTokenGenerator, SystemClock
from src.iam.module import IamModule

logger = logging.getLogger(__name__)

DEFAULT_UNLOCK_PAGE_URL = "http://localhost:3000/unlock"


@dataclass(frozen=True)
class IamSettings:
    """Налаштування модуля IAM.

    Attributes:
        unlock_page_url: Адреса сторінки вебклієнта, на яку веде
            посилання розблокування з листа.
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
) -> IamModule:
    """Створює повністю зібраний модуль IAM.

    Args:
        settings: Налаштування; за замовчуванням ``IamSettings()``.
        clock: Джерело часу; за замовчуванням системний годинник.
        password_hasher: Хешування паролів; за замовчуванням Argon2id.
        email_sender: Пошта; за замовчуванням журнал (лише розробка).
        token_generator: Генератор токенів; за замовчуванням ``secrets``.

    Returns:
        Готовий до використання ``IamModule``.
    """
    settings = settings or IamSettings()
    clock = clock or SystemClock()
    hasher = password_hasher or Argon2PasswordHasher()
    tokens = token_generator or SecretsTokenGenerator()
    if email_sender is None:
        logger.warning(
            "SMTP не налаштовано: листи IAM пишуться в журнал. "
            "Використовуйте це лише для розробки."
        )
        email_sender = LoggingEmailSender()

    users = InMemoryUserRepository()
    sessions = InMemorySessionRepository()
    unlock_tokens = InMemoryUnlockTokenRepository()

    session_issuer = SessionIssuer(
        sessions, tokens, clock, settings.session_policy
    )
    unlock_notifier = UnlockNotifier(
        unlock_tokens, tokens, email_sender, settings.unlock_page_url
    )
    return IamModule(
        register=RegisterUser(
            users, hasher, session_issuer, clock, settings.password_policy
        ),
        login=LoginUser(
            users,
            hasher,
            session_issuer,
            unlock_notifier,
            clock,
            settings.lockout_policy,
        ),
        logout=LogoutUser(sessions),
        verify_session=VerifySession(
            sessions, users, clock, settings.session_policy
        ),
        unlock=UnlockAccount(users, unlock_tokens, clock),
    )


# File was created by Claude (AI-assisted); review by a team member pending.
