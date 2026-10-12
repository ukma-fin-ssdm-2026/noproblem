"""Сценарій «Перевірка токена» (інтерфейс I-02: Шлюз → IAM)."""

from __future__ import annotations

from src.iam.application.dto import UserView
from src.iam.application.ports import Clock, SessionRepository, UserRepository
from src.iam.domain.errors import InvalidSessionError
from src.iam.domain.policies import SessionPolicy
from src.iam.domain.tokens import hash_token

# Токени, що видає ``SecretsTokenGenerator``, мають 43 символи. Довші
# рядки відкидаються одразу, без хешування (дешевий захист від сміття).
_MAX_TOKEN_LENGTH = 256


class VerifySession:
    """Перетворює токен із запиту на автентифікованого користувача.

    Відповідає лише на питання «хто це?» (автентифікація). Чи може цей
    користувач працювати з конкретним документом (авторизація),
    вирішуватиме окремий сценарій керування доступом (частина 2).
    """

    def __init__(
        self,
        sessions: SessionRepository,
        users: UserRepository,
        clock: Clock,
        policy: SessionPolicy,
    ) -> None:
        self._sessions = sessions
        self._users = users
        self._clock = clock
        self._policy = policy

    def execute(self, token: str) -> UserView:
        """Перевіряє токен і продовжує сесію.

        Args:
            token: Токен із заголовка ``Authorization: Bearer``.

        Returns:
            Публічні дані власника сесії.

        Raises:
            InvalidSessionError: Токен невідомий, відкликаний або
                прострочений (за бездіяльністю чи абсолютним строком).
        """
        if not token or len(token) > _MAX_TOKEN_LENGTH:
            raise InvalidSessionError()
        session = self._sessions.get_by_token_hash(hash_token(token))
        if session is None:
            raise InvalidSessionError()

        now = self._clock.now()
        if session.is_expired(now, self._policy):
            # Прострочена сесія видаляється одразу при виявленні, щоб
            # сховище не накопичувало мертві записи.
            self._sessions.delete(session.id)
            raise InvalidSessionError()

        user = self._users.get_by_id(session.user_id)
        if user is None:
            self._sessions.delete(session.id)
            raise InvalidSessionError()

        if session.needs_touch(now, self._policy):
            self._sessions.save(session.touched(now))
        return UserView.from_user(user)


# File was created by Claude (AI-assisted); review by a team member pending.
