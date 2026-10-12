"""Тести адаптера Argon2 зі справжньою бібліотекою ``argon2-cffi``.

Параметри зменшено, щоб тест ішов швидко; поведінка та сама.
"""

from __future__ import annotations

from src.iam.adapters import Argon2PasswordHasher

FAST = {"time_cost": 1, "memory_cost": 8, "parallelism": 1}


def test_hash_is_salted_argon2id_and_verifies() -> None:
    hasher = Argon2PasswordHasher(**FAST)
    first = hasher.hash("correct-horse")
    second = hasher.hash("correct-horse")
    assert first.startswith("$argon2id$")
    assert first != second  # різна сіль → різні хеші
    assert hasher.verify(first, "correct-horse")


def test_wrong_password_returns_false_not_exception() -> None:
    hasher = Argon2PasswordHasher(**FAST)
    assert not hasher.verify(hasher.hash("correct-horse"), "wrong")


def test_corrupted_hash_fails_securely() -> None:
    hasher = Argon2PasswordHasher(**FAST)
    assert not hasher.verify("not-a-hash", "anything")
    assert hasher.needs_rehash("not-a-hash")


def test_weaker_parameters_need_rehash() -> None:
    old = Argon2PasswordHasher(**FAST).hash("correct-horse")
    stronger = Argon2PasswordHasher(time_cost=2, memory_cost=16)
    assert stronger.needs_rehash(old)


# File was created by Claude. Reviewed by Kozynska Anastasia
