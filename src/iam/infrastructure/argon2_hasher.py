"""Хешування паролів алгоритмом Argon2id (бібліотека ``argon2-cffi``).

Чому Argon2id. Це переможець Password Hashing Competition і перший
вибір у OWASP Password Storage Cheat Sheet. Алгоритм навмисно
повільний і потребує багато пам'яті, тому перебір на GPU стає дорогим.
bcrypt теж прийнятний, але обрізає пароль до 72 байтів, а scrypt
складніший у налаштуванні.

Чому сторонній пакет, а не власна реалізація: криптографію не пишуть
самостійно. ``argon2-cffi`` — обгортка над еталонною C-реалізацією,
активно підтримується (організація hynek на GitHub), має ліцензію MIT
і жодних транзитивних залежностей, крім ``argon2-cffi-bindings``.

Залежність від пакета ізольовано в цьому файлі: решта IAM бачить лише
порт ``PasswordHasher``.
"""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    """Реалізує ``PasswordHasher`` через Argon2id.

    Параметри за замовчуванням — профіль RFC 9106 «low memory», який
    застосовує ``argon2-cffi`` (t=3, m=64 MiB, p=4). Для швидких тестів
    їх можна зменшити через аргументи конструктора.
    """

    def __init__(
        self,
        time_cost: int | None = None,
        memory_cost: int | None = None,
        parallelism: int | None = None,
    ) -> None:
        overrides = {
            name: value
            for name, value in (
                ("time_cost", time_cost),
                ("memory_cost", memory_cost),
                ("parallelism", parallelism),
            )
            if value is not None
        }
        self._hasher = _Argon2(**overrides)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            # VerifyMismatchError (неправильний пароль) — підклас
            # VerificationError. Пошкоджений хеш теж означає «не пустити»
            # (принцип fail securely), а не 500.
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True


# File was created by Claude (AI-assisted); review by a team member pending.
