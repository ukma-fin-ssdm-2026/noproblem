"""Додаткові тести для покриття: models.py і service.py.

Кожен тест побудовано за схемою AAA (Arrange / Act / Assert), а назва
читається як речення про поведінку.

Що тут є з вимог завдання:
    * параметризований тест — ``test_lockout_policy_...``;
    * фікстура — ``spied``;
    * дублер — ``Mock(wraps=...)`` замість сховища користувачів;
    * граничний випадок — пароль рівно зі 128 символів.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import Mock

import pytest

from src.iam.adapters import (
    InMemorySessionRepository,
    InMemoryUnlockTokenRepository,
    InMemoryUserRepository,
    SecretsTokenGenerator,
)
from src.iam.errors import InvalidSessionError
from src.iam.models import LockoutPolicy, PasswordPolicy, SessionPolicy
from src.iam.service import AuthService, hash_token
from tests.conftest import VALID_EMAIL, VALID_NAME, VALID_PASSWORD
from tests.fakes import FakeClock, FakePasswordHasher, RecordingEmailSender

#
# Параметризований тест (models.py)
#


@pytest.mark.parametrize(
    ("max_attempts", "duration"),
    [
        (0, timedelta(minutes=15)),  # жодної спроби — безглуздо
        (5, timedelta(0)),  # блокування на 0 секунд
        (5, timedelta(minutes=-1)),  # від'ємна тривалість
    ],
)
def test_lockout_policy_with_nonsensical_settings_cannot_be_created(
    max_attempts: int, duration: timedelta
) -> None:
    # Arrange: некоректні параметри прийшли з parametrize.
    # Act + Assert
    with pytest.raises(ValueError):
        LockoutPolicy(max_failed_attempts=max_attempts, lock_duration=duration)


#
# Граничний випадок (models.py)
#


def test_password_of_exactly_max_length_is_accepted() -> None:
    # Arrange
    policy = PasswordPolicy()
    password = "x" * policy.max_length  # 128 — ще можна, 129 — вже ні

    # Act + Assert: не має кинути виняток.
    policy.check(password)


#
# Фікстура + дублер (service.py)
#


@dataclass
class SpiedService:
    """Сервіс зі справжніми сховищами, але users обгорнуто в Mock."""

    service: AuthService
    users: Mock
    sessions: InMemorySessionRepository


@pytest.fixture
def spied() -> SpiedService:
    """Фікстура: AuthService, де сховище користувачів — дублер.

    ``Mock(wraps=...)`` поводиться як справжнє сховище, доки тест не
    задасть ``return_value`` — тоді метод стає заглушкою.
    """
    users = Mock(wraps=InMemoryUserRepository())
    sessions = InMemorySessionRepository()
    service = AuthService(
        users=users,
        sessions=sessions,
        unlock_tokens=InMemoryUnlockTokenRepository(),
        hasher=FakePasswordHasher(),
        tokens=SecretsTokenGenerator(),
        email_sender=RecordingEmailSender(),
        clock=FakeClock(),
        password_policy=PasswordPolicy(),
        lockout_policy=LockoutPolicy(),
        session_policy=SessionPolicy(),
        unlock_page_url="http://test/unlock",
    )
    return SpiedService(service=service, users=users, sessions=sessions)


def test_session_of_deleted_user_is_rejected_and_removed(
    spied: SpiedService,
) -> None:
    """Жовтий рядок ``if user is None:`` у verify_session стає зеленим."""
    # Arrange
    token = spied.service.register(
        VALID_EMAIL, VALID_NAME, VALID_PASSWORD
    ).session.access_token
    spied.users.get_by_id.return_value = None  # користувача «видалили»

    # Act
    with pytest.raises(InvalidSessionError):
        spied.service.verify_session(token)

    # Assert: «осиротілу» сесію прибрано зі сховища.
    assert spied.sessions.get_by_token_hash(hash_token(token)) is None

