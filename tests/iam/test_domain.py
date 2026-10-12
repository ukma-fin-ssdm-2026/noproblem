"""Модульні тести доменного шару IAM: без FastAPI, без сховищ."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from src.iam.domain.errors import (
    InvalidEmailError,
    InvalidNameError,
    PasswordTooLongError,
    PasswordTooShortError,
)
from src.iam.domain.models import DisplayName, Email, Session, User
from src.iam.domain.policies import (
    LockoutPolicy,
    PasswordPolicy,
    SessionPolicy,
)
from tests.fakes import START_TIME


def make_user() -> User:
    return User(
        id=uuid4(),
        email=Email.parse("olena@example.com"),
        name=DisplayName.parse("Олена"),
        password_hash="hash",
        created_at=START_TIME,
    )


class TestEmail:
    def test_normalizes_case_and_whitespace(self) -> None:
        assert Email.parse("  Olena@Example.COM ").value == "olena@example.com"

    def test_same_address_in_different_case_is_equal(self) -> None:
        assert Email.parse("A@b.co") == Email.parse("a@B.CO")

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "olena",
            "olena@",
            "@example.com",
            "olena@example",
            "olena@@example.com",
            "ole na@example.com",
            "olena@.example.com",
            "olena@example.com.",
            "olena@example..com",
            "a" * 250 + "@example.com",
        ],
    )
    def test_rejects_malformed(self, raw: str) -> None:
        with pytest.raises(InvalidEmailError):
            Email.parse(raw)


class TestDisplayName:
    def test_strips_whitespace(self) -> None:
        assert DisplayName.parse("  Олена ").value == "Олена"

    @pytest.mark.parametrize("raw", ["", "   ", "я" * 101])
    def test_rejects_empty_or_too_long(self, raw: str) -> None:
        with pytest.raises(InvalidNameError):
            DisplayName.parse(raw)

    def test_accepts_exactly_max_length(self) -> None:
        assert len(DisplayName.parse("я" * 100).value) == 100


class TestPasswordPolicy:
    def test_seven_characters_is_too_short(self) -> None:
        # Граничне значення FR-001: 7 — відмова, 8 — дозволено.
        with pytest.raises(PasswordTooShortError) as error:
            PasswordPolicy().check("1234567")
        assert error.value.min_length == 8

    def test_eight_characters_is_enough(self) -> None:
        PasswordPolicy().check("12345678")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(PasswordTooLongError):
            PasswordPolicy().check("x" * 129)

    def test_invalid_configuration_fails_fast(self) -> None:
        with pytest.raises(ValueError):
            PasswordPolicy(min_length=10, max_length=5)


class TestLockout:
    policy = LockoutPolicy()

    def test_four_failures_do_not_lock(self) -> None:
        user = make_user()
        for _ in range(4):
            user = user.with_failed_login(START_TIME, self.policy)
        assert user.failed_login_attempts == 4
        assert not user.is_locked(START_TIME)

    def test_fifth_failure_locks_for_fifteen_minutes(self) -> None:
        user = make_user()
        for _ in range(5):
            user = user.with_failed_login(START_TIME, self.policy)
        assert user.is_locked(START_TIME)
        assert user.locked_until == START_TIME + timedelta(minutes=15)
        # Лічильник скинуто: після блокування знову доступні 5 спроб.
        assert user.failed_login_attempts == 0

    def test_lock_expires_exactly_at_locked_until(self) -> None:
        user = make_user()
        for _ in range(5):
            user = user.with_failed_login(START_TIME, self.policy)
        end = START_TIME + timedelta(minutes=15)
        assert user.is_locked(end - timedelta(seconds=1))
        assert not user.is_locked(end)

    def test_clearing_resets_counter_and_lock(self) -> None:
        user = make_user().with_failed_login(START_TIME, self.policy)
        cleared = user.with_lock_cleared()
        assert cleared.failed_login_attempts == 0
        assert cleared.locked_until is None

    def test_entities_are_immutable(self) -> None:
        user = make_user()
        user.with_failed_login(START_TIME, self.policy)
        assert user.failed_login_attempts == 0  # оригінал не змінився

    def test_password_hash_not_in_repr(self) -> None:
        # Сутність, що випадково потрапила в лог, не розкриває хеш.
        user = make_user().with_password_hash("SECRET-HASH-VALUE")
        assert "SECRET-HASH-VALUE" not in repr(user)


class TestSession:
    policy = SessionPolicy()

    def make_session(self) -> Session:
        return Session(
            id=uuid4(),
            user_id=uuid4(),
            token_hash="h",
            created_at=START_TIME,
            last_seen_at=START_TIME,
            expires_at=START_TIME + self.policy.absolute_lifetime,
        )

    def test_expires_after_idle_timeout(self) -> None:
        session = self.make_session()
        idle = self.policy.idle_timeout
        assert not session.is_expired(
            START_TIME + idle - timedelta(seconds=1), self.policy
        )
        assert session.is_expired(START_TIME + idle, self.policy)

    def test_expires_at_absolute_lifetime_even_if_active(self) -> None:
        end = START_TIME + self.policy.absolute_lifetime
        session = self.make_session().touched(end - timedelta(seconds=1))
        assert session.is_expired(end, self.policy)

    def test_invalid_configuration_fails_fast(self) -> None:
        with pytest.raises(ValueError):
            SessionPolicy(
                idle_timeout=timedelta(hours=2),
                absolute_lifetime=timedelta(hours=1),
            )


# File was created by Claude (AI-assisted); review by a team member pending.
