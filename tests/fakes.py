"""Тестові підробки (fakes) для портів IAM.

Підробка — справжня, але спрощена реалізація порту. На відміну від
mock-об'єктів, вона не перевіряє, *які* методи викликали, а просто
поводиться правдоподібно. Тож тести перевіряють поведінку системи, а
не її внутрішню будову, і не ламаються від рефакторингу.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from src.iam.application.ports import EmailDeliveryError, EmailMessage

START_TIME = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)


class FakeClock:
    """Годинник, який стоїть на місці, доки тест його не «перемотає»."""

    def __init__(self, start: datetime = START_TIME) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        """Пересуває час уперед, наприклад ``advance(minutes=15)``."""
        self._now += timedelta(**kwargs)


class FakePasswordHasher:
    """Миттєвий «хеш» замість Argon2, щоб тести йшли мілісекунди.

    Безпечність тут не потрібна. Справжній Argon2 перевіряє окремий
    тест ``test_argon2_hasher.py``.
    """

    PREFIX = "fake-hash$"

    def __init__(self) -> None:
        self.verify_calls = 0
        self.rehash_needed = False
        self._lock = threading.Lock()

    def hash(self, password: str) -> str:
        return self.PREFIX + password[::-1]

    def verify(self, password_hash: str, password: str) -> bool:
        with self._lock:
            self.verify_calls += 1
        return password_hash == self.hash(password)

    def needs_rehash(self, password_hash: str) -> bool:
        return self.rehash_needed


class RecordingEmailSender:
    """«Надсилає» листи в список, з якого тест може їх прочитати."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = fail
        self._lock = threading.Lock()

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise EmailDeliveryError("SMTP недоступний (тест)")
        with self._lock:
            self.sent.append(message)

    def last_unlock_token(self) -> str:
        """Дістає токен розблокування з останнього листа."""
        body = self.sent[-1].body
        return body.split("token=", 1)[1].split()[0]


# File was created by Claude (AI-assisted); review by a team member pending.
