"""Тести інваріантів сховища користувачів у пам'яті."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.iam.adapters import InMemoryUserRepository
from src.iam.errors import EmailAlreadyRegisteredError
from src.iam.models import DisplayName, Email, User
from tests.fakes import START_TIME


@pytest.fixture
def user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def user() -> User:
    return User(
        id=uuid4(),
        email=Email.parse("olena@example.com"),
        name=DisplayName.parse("Олена"),
        password_hash="hash",
        created_at=START_TIME,
    )


@pytest.fixture
def registered_user_repository(
    user_repository: InMemoryUserRepository, user: User
) -> InMemoryUserRepository:
    user_repository.add(user)
    return user_repository


def test_added_user_can_be_retrieved_by_id(
    registered_user_repository: InMemoryUserRepository, user: User
) -> None:
    # Arrange
    repository = registered_user_repository

    # Act
    result = repository.get_by_id(user.id)

    # Assert
    assert result == user


def test_added_user_can_be_retrieved_by_email(
    registered_user_repository: InMemoryUserRepository, user: User
) -> None:
    # Arrange
    repository = registered_user_repository

    # Act
    result = repository.get_by_email(user.email)

    # Assert
    assert result == user


def test_duplicate_email_is_rejected_without_replacing_the_original_user(
    registered_user_repository: InMemoryUserRepository, user: User
) -> None:
    # Arrange
    repository = registered_user_repository
    duplicate = replace(user, id=uuid4())

    # Act
    with pytest.raises(EmailAlreadyRegisteredError):
        repository.add(duplicate)

    # Assert
    assert repository.get_by_email(user.email) == user


def test_update_persists_the_value_returned_by_its_change_stub(
    registered_user_repository: InMemoryUserRepository, user: User
) -> None:
    # Arrange
    repository = registered_user_repository
    updated_user = replace(user, name=DisplayName.parse("Олена Іваненко"))
    change = Mock(return_value=updated_user)

    # Act
    result = repository.update(user.id, change)

    # Assert
    assert result == updated_user
    assert repository.get_by_id(user.id) == updated_user
    change.assert_called_once_with(user)


@pytest.mark.parametrize(
    "changed_identity",
    [
        pytest.param({"id": uuid4()}, id="changed-id"),
        pytest.param(
            {"email": Email.parse("other@example.com")}, id="changed-email"
        ),
    ],
)
def test_update_rejects_changes_to_immutable_identity_fields(
    registered_user_repository: InMemoryUserRepository,
    user: User,
    changed_identity: dict[str, object],
) -> None:
    # Arrange
    repository = registered_user_repository
    changed_user = replace(user, **changed_identity)

    # Act
    with pytest.raises(ValueError, match="не може змінювати id або email"):
        repository.update(user.id, lambda _current: changed_user)

    # Assert
    assert repository.get_by_id(user.id) == user


def test_update_of_a_missing_user_returns_none(
    user_repository: InMemoryUserRepository,
) -> None:
    # Arrange
    repository = user_repository
    missing_user_id = uuid4()
    change = Mock()

    # Act
    result = repository.update(missing_user_id, change)

    # Assert
    assert result is None
    change.assert_not_called()
