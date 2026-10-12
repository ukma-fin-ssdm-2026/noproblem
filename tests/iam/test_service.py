"""Тести ``AuthService``: сценарії автентифікації IAM.

Сервіс збирається через ``build_iam`` із підробками, без FastAPI.
Назви тестів посилаються на вимоги та на тест-кейси з RTM
(``docs/requirements/rtm.md``: Test-09…Test-13).
"""

from __future__ import annotations

import threading
from collections import Counter

import pytest

from src.iam.errors import (
    AccountLockedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidEmailError,
    InvalidSessionError,
    InvalidUnlockTokenError,
    PasswordTooShortError,
)
from tests.conftest import (
    VALID_EMAIL,
    VALID_NAME,
    VALID_PASSWORD,
    IamTestEnv,
)

WRONG_PASSWORD = "wrong-password"


def register(env: IamTestEnv, email: str = VALID_EMAIL) -> str:
    """Реєструє користувача й повертає токен його сесії."""
    result = env.iam.register(email, VALID_NAME, VALID_PASSWORD)
    return result.session.access_token


def fail_login(env: IamTestEnv, times: int) -> None:
    for _ in range(times):
        with pytest.raises(InvalidCredentialsError):
            env.iam.login(VALID_EMAIL, WRONG_PASSWORD)


class TestRegistration:
    def test_creates_account_and_session(self, env: IamTestEnv) -> None:
        """Test-09 / FR-001: акаунт створено, сесія одразу діє."""
        result = env.iam.register(VALID_EMAIL, VALID_NAME, VALID_PASSWORD)
        assert result.user.email == VALID_EMAIL
        assert result.user.name == VALID_NAME
        me = env.iam.verify_session(result.session.access_token)
        assert me.id == result.user.id

    def test_duplicate_email_is_rejected_case_insensitive(
        self, env: IamTestEnv
    ) -> None:
        """Test-10 / FR-002: зайнятий email."""
        register(env)
        with pytest.raises(EmailAlreadyRegisteredError):
            register(env, email="  OLENA@example.com ")

    def test_short_password_is_rejected(self, env: IamTestEnv) -> None:
        """Test-10 / FR-002: пароль коротший за 8 символів."""
        with pytest.raises(PasswordTooShortError):
            env.iam.register(VALID_EMAIL, VALID_NAME, "1234567")
        # Невдала спроба нічого не створила: email вільний.
        register(env)

    def test_malformed_email_is_rejected(self, env: IamTestEnv) -> None:
        with pytest.raises(InvalidEmailError):
            env.iam.register("not-an-email", VALID_NAME, VALID_PASSWORD)

    def test_concurrent_registrations_create_one_account(
        self, env: IamTestEnv
    ) -> None:
        """Атомарність ``add``: з 10 паралельних реєстрацій успішна одна."""
        outcomes: list[str] = []
        barrier = threading.Barrier(10)

        def attempt() -> None:
            barrier.wait()
            try:
                register(env)
                outcomes.append("ok")
            except EmailAlreadyRegisteredError:
                outcomes.append("duplicate")

        threads = [threading.Thread(target=attempt) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert Counter(outcomes) == {"ok": 1, "duplicate": 9}


class TestLogin:
    def test_correct_credentials_create_session(self, env: IamTestEnv) -> None:
        """FR-003."""
        register(env)
        result = env.iam.login(" Olena@Example.com", VALID_PASSWORD)
        assert env.iam.verify_session(result.session.access_token).email == (
            VALID_EMAIL
        )

    def test_every_login_issues_new_token(self, env: IamTestEnv) -> None:
        """Захист від фіксації сесії: щоразу новий токен."""
        first = register(env)
        second = env.iam.login(VALID_EMAIL, VALID_PASSWORD)
        assert first != second.session.access_token

    @pytest.mark.parametrize(
        ("email", "password"),
        [
            (VALID_EMAIL, WRONG_PASSWORD),
            ("nobody@example.com", VALID_PASSWORD),
            ("not-an-email", VALID_PASSWORD),
        ],
    )
    def test_any_failure_is_the_same_generic_error(
        self, env: IamTestEnv, email: str, password: str
    ) -> None:
        """Test-11 / FR-004: однаковий виняток для всіх причин."""
        register(env)
        with pytest.raises(InvalidCredentialsError):
            env.iam.login(email, password)

    def test_unknown_email_still_runs_password_check(
        self, env: IamTestEnv
    ) -> None:
        """Захист від атаки за часом: хеш перевіряється і без акаунта."""
        calls_before = env.hasher.verify_calls
        with pytest.raises(InvalidCredentialsError):
            env.iam.login("nobody@example.com", VALID_PASSWORD)
        assert env.hasher.verify_calls == calls_before + 1

    def test_outdated_hash_is_upgraded_on_login(self, env: IamTestEnv) -> None:
        register(env)
        env.hasher.rehash_needed = True
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)
        env.hasher.rehash_needed = False
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)


class TestLockout:
    def test_fifth_failure_locks_account(self, env: IamTestEnv) -> None:
        """Test-12 / FR-005 / NFR-SEC-003."""
        register(env)
        fail_login(env, 5)
        # Навіть правильний пароль тепер відхиляється.
        with pytest.raises(AccountLockedError) as error:
            env.iam.login(VALID_EMAIL, VALID_PASSWORD)
        assert error.value.retry_after_seconds == 15 * 60

    def test_four_failures_do_not_lock(self, env: IamTestEnv) -> None:
        register(env)
        fail_login(env, 4)
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)

    def test_success_resets_consecutive_counter(self, env: IamTestEnv) -> None:
        """«5 послідовних» спроб: успіх посередині обнуляє лічильник."""
        register(env)
        fail_login(env, 4)
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)
        fail_login(env, 4)
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)

    def test_lock_lifts_after_fifteen_minutes(self, env: IamTestEnv) -> None:
        register(env)
        fail_login(env, 5)
        env.clock.advance(minutes=14, seconds=59)
        with pytest.raises(AccountLockedError):
            env.iam.login(VALID_EMAIL, VALID_PASSWORD)
        env.clock.advance(seconds=1)
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)

    def test_attempts_during_lock_do_not_extend_it(
        self, env: IamTestEnv
    ) -> None:
        register(env)
        fail_login(env, 5)
        for _ in range(10):
            with pytest.raises(AccountLockedError):
                env.iam.login(VALID_EMAIL, WRONG_PASSWORD)
        env.clock.advance(minutes=15)
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)

    def test_parallel_attack_gets_exactly_five_attempts(
        self, env: IamTestEnv
    ) -> None:
        """Гонка потоків не дає зловмиснику зайвих спроб (NFR-SEC-003)."""
        register(env)
        outcomes: list[str] = []
        barrier = threading.Barrier(20)

        def attempt() -> None:
            barrier.wait()
            try:
                env.iam.login(VALID_EMAIL, WRONG_PASSWORD)
            except InvalidCredentialsError:
                outcomes.append("checked")
            except AccountLockedError:
                outcomes.append("locked")

        threads = [threading.Thread(target=attempt) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert Counter(outcomes) == {"checked": 5, "locked": 15}
        assert len(env.mail.sent) == 1


class TestUnlockByEmail:
    def test_lock_sends_one_email_with_link(self, env: IamTestEnv) -> None:
        register(env)
        fail_login(env, 5)
        assert len(env.mail.sent) == 1
        message = env.mail.sent[0]
        assert message.recipient == VALID_EMAIL
        assert "unlock?token=" in message.body

    def test_link_unlocks_immediately_and_only_once(
        self, env: IamTestEnv
    ) -> None:
        register(env)
        fail_login(env, 5)
        token = env.mail.last_unlock_token()
        env.iam.unlock_account(token)
        env.iam.login(VALID_EMAIL, VALID_PASSWORD)
        with pytest.raises(InvalidUnlockTokenError):
            env.iam.unlock_account(token)

    def test_link_expires_with_the_lock(self, env: IamTestEnv) -> None:
        register(env)
        fail_login(env, 5)
        token = env.mail.last_unlock_token()
        env.clock.advance(minutes=15)
        with pytest.raises(InvalidUnlockTokenError):
            env.iam.unlock_account(token)

    def test_unknown_token_is_rejected(self, env: IamTestEnv) -> None:
        with pytest.raises(InvalidUnlockTokenError):
            env.iam.unlock_account("made-up-token")

    def test_mail_failure_does_not_cancel_lock(self, env: IamTestEnv) -> None:
        """I-19: збій пошти обробляється, але блокування діє."""
        register(env)
        env.mail.fail = True
        fail_login(env, 5)  # 5-та спроба все одно 401, не 500
        with pytest.raises(AccountLockedError):
            env.iam.login(VALID_EMAIL, VALID_PASSWORD)


class TestSessions:
    def test_logout_invalidates_token_immediately(
        self, env: IamTestEnv
    ) -> None:
        """Test-13 / FR-006."""
        token = register(env)
        env.iam.logout(token)
        with pytest.raises(InvalidSessionError):
            env.iam.verify_session(token)

    def test_logout_is_idempotent(self, env: IamTestEnv) -> None:
        token = register(env)
        env.iam.logout(token)
        env.iam.logout(token)

    def test_logout_ends_only_current_session(self, env: IamTestEnv) -> None:
        laptop = register(env)
        phone = env.iam.login(VALID_EMAIL, VALID_PASSWORD).session
        env.iam.logout(laptop)
        env.iam.verify_session(phone.access_token)

    @pytest.mark.parametrize("token", ["", "x" * 1000, "unknown-token"])
    def test_invalid_tokens_are_rejected(
        self, env: IamTestEnv, token: str
    ) -> None:
        with pytest.raises(InvalidSessionError):
            env.iam.verify_session(token)

    def test_idle_session_expires_after_30_minutes(
        self, env: IamTestEnv
    ) -> None:
        token = register(env)
        env.clock.advance(minutes=30)
        with pytest.raises(InvalidSessionError):
            env.iam.verify_session(token)

    def test_activity_keeps_session_alive(self, env: IamTestEnv) -> None:
        token = register(env)
        for _ in range(5):
            env.clock.advance(minutes=20)
            env.iam.verify_session(token)

    def test_absolute_lifetime_ends_active_session(
        self, env: IamTestEnv
    ) -> None:
        token = register(env)
        for _ in range(35):  # 35 × 20 хв = 11 год 40 хв
            env.clock.advance(minutes=20)
            env.iam.verify_session(token)
        env.clock.advance(minutes=20)  # 12 год від входу
        with pytest.raises(InvalidSessionError):
            env.iam.verify_session(token)


# File was created by Claude. Reviewed by Kozynska Anastasia
