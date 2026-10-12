"""Політики безпеки IAM: параметри, які задають бізнес-правила.

Числа з вимог (8 символів, 5 спроб, 15 хвилин) зібрано в одному місці,
а не розкидано по коду як «магічні числа». Політики незмінні
(``frozen=True``) і перевіряють свої параметри при створенні, тож
некоректна конфігурація падає одразу під час запуску, а не посеред
обробки запиту.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from src.iam.domain.errors import PasswordTooLongError, PasswordTooShortError


@dataclass(frozen=True)
class PasswordPolicy:
    """Вимоги до пароля.

    Attributes:
        min_length: Мінімальна довжина (FR-001: 8 символів).
        max_length: Максимальна довжина. Обмежує обсяг роботи хеш-функції
            на один запит, щоб довгі паролі не стали вектором DoS.
    """

    min_length: int = 8
    max_length: int = 128

    def __post_init__(self) -> None:
        if not 1 <= self.min_length <= self.max_length:
            raise ValueError("Потрібно 1 <= min_length <= max_length.")

    def check(self, password: str) -> None:
        """Перевіряє пароль на відповідність політиці.

        Склад пароля (цифри, великі літери тощо) свідомо не
        перевіряється: сучасні рекомендації NIST SP 800-63B радять
        вимагати довжину, а не «складність».

        Args:
            password: Пароль у відкритому вигляді.

        Raises:
            PasswordTooShortError: Пароль коротший за ``min_length``.
            PasswordTooLongError: Пароль довший за ``max_length``.
        """
        if len(password) < self.min_length:
            raise PasswordTooShortError(self.min_length)
        if len(password) > self.max_length:
            raise PasswordTooLongError(self.max_length)


@dataclass(frozen=True)
class LockoutPolicy:
    """Правила тимчасового блокування входу (FR-005, NFR-SEC-003).

    Attributes:
        max_failed_attempts: Кількість послідовних невдалих спроб, після
            якої вхід блокується.
        lock_duration: Тривалість блокування.
    """

    max_failed_attempts: int = 5
    lock_duration: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if self.max_failed_attempts < 1:
            raise ValueError("max_failed_attempts має бути >= 1.")
        if self.lock_duration <= timedelta(0):
            raise ValueError("lock_duration має бути додатною.")


@dataclass(frozen=True)
class SessionPolicy:
    """Строки життя сесії.

    Два незалежні таймаути — рекомендація OWASP Session Management:
    сесія закінчується або після періоду бездіяльності, або після
    абсолютного строку, залежно від того, що настане раніше.

    Attributes:
        idle_timeout: Скільки сесія живе без жодного запиту.
        absolute_lifetime: Максимальний строк сесії від моменту входу.
        touch_interval: Як часто оновлювати «останню активність».
            Без цього кожен запит означав би запис у БД.
    """

    idle_timeout: timedelta = timedelta(minutes=30)
    absolute_lifetime: timedelta = timedelta(hours=12)
    touch_interval: timedelta = timedelta(minutes=1)

    def __post_init__(self) -> None:
        if self.idle_timeout <= timedelta(0):
            raise ValueError("idle_timeout має бути додатним.")
        if self.absolute_lifetime < self.idle_timeout:
            raise ValueError("absolute_lifetime має бути >= idle_timeout.")
        if not timedelta(0) <= self.touch_interval < self.idle_timeout:
            raise ValueError("touch_interval має бути менше idle_timeout.")


# File was created by Claude (AI-assisted); review by a team member pending.
