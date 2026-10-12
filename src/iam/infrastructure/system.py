"""Адаптери до системних ресурсів: годинник і генератор токенів."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


class SystemClock:
    """Реалізує ``Clock``: реальний час в UTC.

    Час завжди «aware» (з часовим поясом). Порівнювати aware-час із
    naive не можна (Python кидає ``TypeError``), тож UTC скрізь
    захищає від тонких помилок із часовими поясами.
    """

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SecretsTokenGenerator:
    """Реалізує ``TokenGenerator`` через модуль ``secrets``.

    ``secrets`` бере випадковість з ОС (CSPRNG). Модуль ``random`` для
    цього не підходить: він передбачуваний (Bandit B311). 32 байти =
    256 біт ентропії, у base64url — 43 символи.
    """

    def __init__(self, num_bytes: int = 32) -> None:
        if num_bytes < 16:
            raise ValueError("Токен має містити щонайменше 128 біт.")
        self._num_bytes = num_bytes

    def new_token(self) -> str:
        return secrets.token_urlsafe(self._num_bytes)


# File was created by Claude (AI-assisted); review by a team member pending.
