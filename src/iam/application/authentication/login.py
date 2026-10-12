"""Сценарій «Вхід» (FR-003, FR-004, FR-005, NFR-SEC-003).

Логіка повторює діаграму послідовності
``docs/architecture/uml/sequence_diagram.puml``:

1. акаунт заблоковано → ``AccountLockedError`` (HTTP 423);
2. пароль неправильний або акаунта немає → лічильник +1, на 5-й
   спробі поспіль блокування й лист → ``InvalidCredentialsError`` (401);
3. дані правильні → лічильник скидається, створюється сесія (200).
"""

from __future__ import annotations

import secrets
from datetime import datetime

from src.iam.application.audit import security_log
from src.iam.application.authentication.sessions import SessionIssuer
from src.iam.application.authentication.unlock import UnlockNotifier
from src.iam.application.dto import AuthResult, UserView
from src.iam.application.ports import Clock, PasswordHasher, UserRepository
from src.iam.domain.errors import (
    AccountLockedError,
    InvalidCredentialsError,
    InvalidEmailError,
)
from src.iam.domain.models import Email, User
from src.iam.domain.policies import LockoutPolicy


class LoginUser:
    """Перевіряє email і пароль та видає сесію."""

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        session_issuer: SessionIssuer,
        unlock_notifier: UnlockNotifier,
        clock: Clock,
        lockout_policy: LockoutPolicy,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._session_issuer = session_issuer
        self._unlock_notifier = unlock_notifier
        self._clock = clock
        self._lockout_policy = lockout_policy
        # Хеш випадкового пароля для вирівнювання часу відповіді (нижче).
        self._dummy_hash = hasher.hash(secrets.token_urlsafe(16))

    def execute(self, email: str, password: str) -> AuthResult:
        """Виконує вхід.

        Args:
            email: Email, введений користувачем.
            password: Пароль у відкритому вигляді.

        Returns:
            Дані користувача та токен нової сесії.

        Raises:
            InvalidCredentialsError: Невірна пара email/пароль (FR-004).
            AccountLockedError: Вхід тимчасово заблоковано (FR-005).
        """
        user = self._find_user(email)
        if user is None:
            # Захист від атаки за часом (timing attack): без цього
            # відповідь для неіснуючого email приходила б помітно
            # швидше (без ~50 мс Argon2), і зловмисник дізнавався б,
            # які email зареєстровані, попри однакове повідомлення.
            self._hasher.verify(self._dummy_hash, password)
            security_log.warning("login_failed reason=unknown_account")
            raise InvalidCredentialsError()

        now = self._clock.now()
        if user.is_locked(now):
            security_log.warning("login_rejected_locked user_id=%s", user.id)
            raise AccountLockedError(_locked_until(user), now)

        # Повільна перевірка пароля відбувається ДО атомарного оновлення,
        # щоб не тримати блокування рядка під час хешування.
        if self._hasher.verify(user.password_hash, password):
            return self._on_success(user, password, now)
        self._on_failure(user, now)
        raise InvalidCredentialsError()

    def _find_user(self, email: str) -> User | None:
        try:
            return self._users.get_by_email(Email.parse(email))
        except InvalidEmailError:
            return None

    def _on_success(
        self, user: User, password: str, now: datetime
    ) -> AuthResult:
        new_hash = None
        if self._hasher.needs_rehash(user.password_hash):
            # Параметри Argon2 посилили, тож оновлюємо хеш, поки пароль
            # у відкритому вигляді доступний (тільки під час входу).
            new_hash = self._hasher.hash(password)

        def apply(current: User) -> User:
            # Повторна перевірка вже під атомарним оновленням: між
            # першою перевіркою і цим моментом паралельні невдалі
            # спроби могли заблокувати акаунт.
            if current.is_locked(now):
                raise AccountLockedError(_locked_until(current), now)
            updated = current.with_lock_cleared()
            if new_hash is not None:
                updated = updated.with_password_hash(new_hash)
            return updated

        updated = self._users.update(user.id, apply)
        if updated is None:
            raise InvalidCredentialsError()
        session = self._session_issuer.issue(updated.id)
        security_log.info("login_succeeded user_id=%s", updated.id)
        return AuthResult(user=UserView.from_user(updated), session=session)

    def _on_failure(self, user: User, now: datetime) -> None:
        def apply(current: User) -> User:
            if current.is_locked(now):
                raise AccountLockedError(_locked_until(current), now)
            return current.with_failed_login(now, self._lockout_policy)

        updated = self._users.update(user.id, apply)
        if updated is None:
            return
        if updated.is_locked(now):
            # Ця спроба була останньою дозволеною. На діаграмі послідовності
            # вона ще отримує 401, а наступні вже 423.
            security_log.warning(
                "account_locked user_id=%s until=%s",
                updated.id,
                _locked_until(updated).isoformat(),
            )
            self._unlock_notifier.notify(updated)
        else:
            security_log.warning(
                "login_failed reason=wrong_password user_id=%s attempts=%d",
                updated.id,
                updated.failed_login_attempts,
            )


def _locked_until(user: User) -> datetime:
    # ``is_locked`` гарантує, що поле заповнене; перевірка потрібна для
    # статичного аналізу типів і на випадок помилки виклику.
    if user.locked_until is None:
        raise ValueError("Користувач не заблокований.")
    return user.locked_until


# File was created by Claude (AI-assisted); review by a team member pending.
