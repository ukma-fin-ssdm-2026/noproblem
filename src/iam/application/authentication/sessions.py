"""Видача нових сесій.

Спільна частина для реєстрації та входу. Винесена окремо, щоб правило
«як створюється сесія» існувало в одному місці (принцип DRY).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from src.iam.application.dto import IssuedSession
from src.iam.application.ports import Clock, SessionRepository, TokenGenerator
from src.iam.domain.models import Session
from src.iam.domain.policies import SessionPolicy
from src.iam.domain.tokens import hash_token


class SessionIssuer:
    """Створює сесію та повертає клієнту одноразово видимий токен."""

    def __init__(
        self,
        sessions: SessionRepository,
        tokens: TokenGenerator,
        clock: Clock,
        policy: SessionPolicy,
    ) -> None:
        self._sessions = sessions
        self._tokens = tokens
        self._clock = clock
        self._policy = policy

    def issue(self, user_id: UUID) -> IssuedSession:
        """Створює нову сесію для користувача.

        Кожен вхід отримує *новий* токен. Це захищає від атаки
        фіксації сесії (session fixation): токен, відомий
        зловмиснику до входу, після входу недійсний.

        Args:
            user_id: Ідентифікатор користувача, що пройшов перевірку.

        Returns:
            Токен доступу та момент абсолютного завершення сесії.
        """
        now = self._clock.now()
        token = self._tokens.new_token()
        session = Session(
            id=uuid4(),
            user_id=user_id,
            token_hash=hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._policy.absolute_lifetime,
        )
        self._sessions.add(session)
        return IssuedSession(access_token=token, expires_at=session.expires_at)


# File was created by Claude (AI-assisted); review by a team member pending.
