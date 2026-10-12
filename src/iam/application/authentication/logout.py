"""Сценарій «Вихід» (FR-006)."""

from __future__ import annotations

from src.iam.application.audit import security_log
from src.iam.application.ports import SessionRepository
from src.iam.domain.tokens import hash_token


class LogoutUser:
    """Завершує сесію на сервері.

    Сесія видаляється зі сховища, тож уже наступний запит із цим
    токеном отримає 401. Це виконує вимогу FR-006 «інвалідувати
    протягом 1 секунди» з великим запасом. Видалити лише токен у
    браузері недостатньо: копія токена (наприклад, украдена) лишилася
    б чинною.
    """

    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    def execute(self, token: str) -> None:
        """Видаляє сесію з цим токеном.

        Операція ідемпотентна: повторний вихід не є помилкою.

        Args:
            token: Токен сесії з заголовка ``Authorization``.
        """
        if self._sessions.delete_by_token_hash(hash_token(token)):
            security_log.info("logout")


# File was created by Claude (AI-assisted); review by a team member pending.
