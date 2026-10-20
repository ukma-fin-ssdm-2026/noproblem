"""Тести ``AccessService``: ролі Owner / Editor / Guest (FR-040–FR-043).

NFR-SEC-001 і NFR-SEC-004 вимагають «у 100% тестових сценаріїв», тому
нижче перевірено кожну комбінацію «роль × дія». Очікувані права
виписано окремо від ``ROLE_PERMISSIONS`` у коді: інакше тест порівнював
би таблицю саму з собою.
"""

from __future__ import annotations

import logging

import pytest

from src.iam import Action, Role, UserView
from src.iam.errors import (
    AccessDeniedError,
    OwnerAccessChangeError,
    UserNotFoundError,
)
from tests.conftest import VALID_PASSWORD, IamTestEnv

DOC = 1

EXPECTED = {
    Role.OWNER: {Action.VIEW, Action.EDIT, Action.TRASH, Action.MANAGE_ACCESS},
    Role.EDITOR: {Action.VIEW, Action.EDIT},
    Role.GUEST: {Action.VIEW},
}


def user(env: IamTestEnv, email: str) -> UserView:
    return env.iam.register(email, email.split("@")[0], VALID_PASSWORD).user


@pytest.fixture
def owner(env: IamTestEnv) -> UserView:
    olena = user(env, "olena@example.com")
    env.access.grant_owner(DOC, olena.id)
    return olena


@pytest.mark.parametrize(
    ("role", "action"),
    [(role, action) for role in Role for action in Action],
)
def test_role_matrix(
    env: IamTestEnv, owner: UserView, role: Role, action: Action
) -> None:
    """Кожна роль може рівно те, що записано у вимогах."""
    if role is Role.OWNER:
        member = owner
    else:
        member = user(env, "andrii@example.com")
        env.access.share(owner.id, DOC, member.email, role)
    allowed = env.access.has_permission(member.id, DOC, action)
    assert allowed is (action in EXPECTED[role])


@pytest.mark.parametrize("action", list(Action))
def test_stranger_is_denied_everything(
    env: IamTestEnv, owner: UserView, action: Action
) -> None:
    """NFR-SEC-001: без ролі немає жодного доступу (default deny)."""
    stranger = user(env, "marko@example.com")
    with pytest.raises(AccessDeniedError):
        env.access.check(stranger.id, DOC, action)


def test_denial_is_logged(
    env: IamTestEnv, owner: UserView, caplog: pytest.LogCaptureFixture
) -> None:
    """Спроби неавторизованого доступу логуються (S-SEC-002)."""
    stranger = user(env, "marko@example.com")
    with caplog.at_level(logging.WARNING, logger="notely.security"):
        with pytest.raises(AccessDeniedError):
            env.access.check(stranger.id, DOC, Action.VIEW)
    assert "access_denied" in caplog.text


def test_only_owner_can_share(env: IamTestEnv, owner: UserView) -> None:
    """NFR-SEC-004: не-власник не може змінювати права."""
    editor = user(env, "andrii@example.com")
    user(env, "marko@example.com")
    env.access.share(owner.id, DOC, editor.email, Role.EDITOR)
    with pytest.raises(AccessDeniedError):
        env.access.share(editor.id, DOC, "marko@example.com", Role.GUEST)


# тест 1 від Olha Marushchenko
def test_owner_cannot_grant_owner_role_to_another_user(
    env: IamTestEnv, owner: UserView
) -> None:
    another_user = user(env, "andrii@example.com")

    with pytest.raises(OwnerAccessChangeError):
        env.access.share(owner.id, DOC, another_user.email, Role.OWNER)

    assert env.access.has_permission(owner.id, DOC, Action.MANAGE_ACCESS)
    assert not env.access.has_permission(
        another_user.id, DOC, Action.MANAGE_ACCESS
    )


# тест 2 від Olha Marushchenko
def test_editor_cannot_revoke_access(env: IamTestEnv, owner: UserView) -> None:
    editor = user(env, "andrii@example.com")
    guest = user(env, "marko@example.com")
    env.access.share(owner.id, DOC, editor.email, Role.EDITOR)
    env.access.share(owner.id, DOC, guest.email, Role.GUEST)

    with pytest.raises(AccessDeniedError):
        env.access.revoke(editor.id, DOC, guest.id)

    assert env.access.has_permission(guest.id, DOC, Action.VIEW)


def test_sharing_again_changes_role(env: IamTestEnv, owner: UserView) -> None:
    """FR-043: повторне надання змінює роль."""
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.EDITOR)
    env.access.share(owner.id, DOC, andrii.email, Role.GUEST)
    assert not env.access.has_permission(andrii.id, DOC, Action.EDIT)
    assert env.access.has_permission(andrii.id, DOC, Action.VIEW)


def test_revoke_removes_access(env: IamTestEnv, owner: UserView) -> None:
    """FR-042."""
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.EDITOR)
    env.access.revoke(owner.id, DOC, andrii.id)
    assert not env.access.has_permission(andrii.id, DOC, Action.VIEW)
    assert DOC not in env.access.accessible_document_ids(andrii.id)


def test_unknown_email_is_rejected(env: IamTestEnv, owner: UserView) -> None:
    with pytest.raises(UserNotFoundError):
        env.access.share(owner.id, DOC, "nobody@example.com", Role.GUEST)


def test_owner_role_cannot_be_changed_or_revoked(
    env: IamTestEnv, owner: UserView
) -> None:
    """Інакше документ міг би лишитися без власника."""
    with pytest.raises(OwnerAccessChangeError):
        env.access.share(owner.id, DOC, owner.email, Role.GUEST)
    with pytest.raises(OwnerAccessChangeError):
        env.access.revoke(owner.id, DOC, owner.id)


def test_members_lists_everyone_with_roles(
    env: IamTestEnv, owner: UserView
) -> None:
    andrii = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, andrii.email, Role.GUEST)
    members = {m.user.email: m.role for m in env.access.members(owner.id, DOC)}
    assert members == {owner.email: Role.OWNER, andrii.email: Role.GUEST}


# тест 3 від Olha Marushchenko
def test_guest_cannot_list_members(env: IamTestEnv, owner: UserView) -> None:
    guest = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, guest.email, Role.GUEST)

    with pytest.raises(AccessDeniedError):
        env.access.members(guest.id, DOC)


# [RED] тест 5 від Olha Marushchenko (TDD)
# Made with Copilot


def test_guest_can_see_member_count_without_listing_members(
    env: IamTestEnv, owner: UserView
) -> None:
    editor = user(env, "editor@example.com")
    guest = user(env, "andrii@example.com")
    env.access.share(owner.id, DOC, editor.email, Role.EDITOR)
    env.access.share(owner.id, DOC, guest.email, Role.GUEST)

    assert env.access.member_count(guest.id, DOC) == 3
    with pytest.raises(AccessDeniedError):
        env.access.members(guest.id, DOC)


# File was created by Claude. Reviewed by Kozynska Anastasia and Olha
# Marushchenko.
