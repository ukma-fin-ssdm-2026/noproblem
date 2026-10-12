"""Розблокування акаунта за посиланням з листа (FR-005, I-19)."""

from __future__ import annotations

from urllib.parse import urlencode

from src.iam.application.audit import security_log
from src.iam.application.ports import (
    Clock,
    EmailDeliveryError,
    EmailMessage,
    EmailSender,
    TokenGenerator,
    UnlockTokenRepository,
    UserRepository,
)
from src.iam.domain.errors import InvalidUnlockTokenError
from src.iam.domain.models import UnlockToken, User
from src.iam.domain.tokens import hash_token


class UnlockNotifier:
    """Створює одноразовий токен і надсилає лист із посиланням.

    Посилання веде на сторінку вебклієнта (наприклад,
    ``https://notely.example/unlock?token=...``), а та вже робить
    ``POST /api/v1/auth/unlock``. Чому не прямий ``GET`` на API:

    * ``GET`` має бути безпечним (без побічних ефектів), а
      розблокування змінює стан;
    * поштові антивіруси й попередній перегляд посилань самі
      відкривають ``GET``-посилання й «спалили» б одноразовий токен.
    """

    def __init__(
        self,
        unlock_tokens: UnlockTokenRepository,
        tokens: TokenGenerator,
        email_sender: EmailSender,
        unlock_page_url: str,
    ) -> None:
        self._unlock_tokens = unlock_tokens
        self._tokens = tokens
        self._email_sender = email_sender
        self._unlock_page_url = unlock_page_url

    def notify(self, user: User) -> None:
        """Надсилає лист розблокування заблокованому користувачу.

        Збій пошти не скасовує блокування: воно однаково зніметься
        автоматично через 15 хвилин. Тому помилку записуємо в журнал
        безпеки (не маскуємо, I-19), але далі не передаємо: користувач
        і так отримає відповідь «невірний email або пароль».

        Args:
            user: Користувач, щойно заблокований. ``locked_until`` має
                бути заповнено.
        """
        if user.locked_until is None:
            raise ValueError("Користувач не заблокований.")
        token = self._tokens.new_token()
        # Посилання не має переживати саме блокування: після
        # ``locked_until`` воно вже нічого не змінює.
        self._unlock_tokens.add(
            UnlockToken(
                token_hash=hash_token(token),
                user_id=user.id,
                expires_at=user.locked_until,
            )
        )
        link = f"{self._unlock_page_url}?{urlencode({'token': token})}"
        message = EmailMessage(
            recipient=str(user.email),
            subject="NoteLy: вхід до акаунта тимчасово заблоковано",
            body=(
                f"Вітаємо, {user.name}!\n\n"
                "Ми зафіксували кілька невдалих спроб увійти до вашого "
                "акаунта, тому тимчасово заблокували вхід.\n"
                "Блокування зніметься автоматично. Щоб розблокувати "
                f"акаунт одразу, перейдіть за посиланням:\n{link}\n\n"
                "Якщо це були не ви, радимо змінити пароль."
            ),
        )
        try:
            self._email_sender.send(message)
        except EmailDeliveryError:
            security_log.error(
                "unlock_email_failed user_id=%s", user.id, exc_info=True
            )


class UnlockAccount:
    """Знімає блокування за одноразовим токеном з листа."""

    def __init__(
        self,
        users: UserRepository,
        unlock_tokens: UnlockTokenRepository,
        clock: Clock,
    ) -> None:
        self._users = users
        self._unlock_tokens = unlock_tokens
        self._clock = clock

    def execute(self, token: str) -> None:
        """Розблоковує акаунт.

        Токен видаляється *до* перевірки строку дії (``pop``), тож навіть
        прострочений токен не можна використати повторно.

        Args:
            token: Токен із посилання в листі.

        Raises:
            InvalidUnlockTokenError: Токен невідомий, використаний або
                прострочений.
        """
        stored = self._unlock_tokens.pop(hash_token(token))
        if stored is None or stored.is_expired(self._clock.now()):
            security_log.warning("unlock_rejected")
            raise InvalidUnlockTokenError()
        updated = self._users.update(
            stored.user_id, lambda user: user.with_lock_cleared()
        )
        if updated is None:
            raise InvalidUnlockTokenError()
        security_log.info("account_unlocked user_id=%s", stored.user_id)


# File was created by Claude (AI-assisted); review by a team member pending.
