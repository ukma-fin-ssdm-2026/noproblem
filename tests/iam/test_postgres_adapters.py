"""Спільні перевірки IAM-адаптерів у пам'яті та PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import uuid4

import pytest
from psycopg_pool import ConnectionPool

from src.iam.adapters import (
    InMemoryAccessRepository,
    InMemorySessionRepository,
    InMemoryUnlockTokenRepository,
    InMemoryUserRepository,
    SecretsTokenGenerator,
)
from src.iam.bootstrap import IamSettings
from src.iam.errors import (
    AccountLockedError,
    AccessDeniedError,
    AccessRequestAlreadyPendingError,
    InvalidAccessRequestTransitionError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)
from src.iam.models import (
    AccessRequest,
    AccessRequestStatus,
    AccessRequestType,
    DocumentAccess,
    DisplayName,
    Email,
    Role,
    Session,
    UnlockToken,
    User,
)
from src.iam.ports import (
    AccessRepository,
    SessionRepository,
    UnlockTokenRepository,
    UserRepository,
)
from src.iam.postgres import (
    PostgresAccessRepository,
    PostgresSessionRepository,
    PostgresUnlockTokenRepository,
    PostgresUserRepository,
)
from src.iam.service import AuthService, hash_token
from tests.fakes import (
    FakeClock,
    FakePasswordHasher,
    RecordingEmailSender,
    START_TIME,
)
from tests.conftest import VALID_NAME, VALID_PASSWORD


@dataclass(frozen=True)
class Repositories:
    users: UserRepository
    sessions: SessionRepository
    unlock_tokens: UnlockTokenRepository
    access: AccessRepository


@pytest.fixture(params=["memory", "postgres"])
def repositories(request: pytest.FixtureRequest) -> Repositories:
    if request.param == "memory":
        return Repositories(
            users=InMemoryUserRepository(),
            sessions=InMemorySessionRepository(),
            unlock_tokens=InMemoryUnlockTokenRepository(),
            access=InMemoryAccessRepository(),
        )

    pool: ConnectionPool = request.getfixturevalue("pg_pool")
    return Repositories(
        users=PostgresUserRepository(pool),
        sessions=PostgresSessionRepository(pool),
        unlock_tokens=PostgresUnlockTokenRepository(pool),
        access=PostgresAccessRepository(pool),
    )


def new_user(email: str = "olena@example.com") -> User:
    return User(
        id=uuid4(),
        email=Email.parse(email),
        name=DisplayName.parse(VALID_NAME),
        password_hash="hash",
        created_at=START_TIME,
    )


def test_user_repository_add_lookup_update_and_unique_email(
    repositories: Repositories,
) -> None:
    user = new_user()
    repositories.users.add(user)

    assert repositories.users.get_by_id(user.id) == user
    assert repositories.users.get_by_email(user.email) == user
    with pytest.raises(EmailAlreadyRegisteredError):
        repositories.users.add(replace(user, id=uuid4()))

    updated = repositories.users.update(
        user.id, lambda current: replace(current, failed_login_attempts=3)
    )
    assert updated is not None
    assert updated.failed_login_attempts == 3
    assert repositories.users.get_by_id(user.id) == updated
    assert repositories.users.update(uuid4(), lambda current: current) is None

    with pytest.raises(ValueError, match="не може змінювати id або email"):
        repositories.users.update(
            user.id,
            lambda current: replace(
                current, email=Email.parse("other@example.com")
            ),
        )

    def fail_change(_current: User) -> User:
        raise RuntimeError("rollback")

    with pytest.raises(RuntimeError, match="rollback"):
        repositories.users.update(user.id, fail_change)
    assert repositories.users.get_by_id(user.id) == updated


def test_session_repository_round_trip_touch_and_delete(
    repositories: Repositories,
) -> None:
    user = new_user()
    repositories.users.add(user)
    session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="session-hash",
        created_at=START_TIME,
        last_seen_at=START_TIME,
        expires_at=START_TIME + timedelta(hours=12),
    )
    repositories.sessions.add(session)
    assert (
        repositories.sessions.get_by_token_hash(session.token_hash) == session
    )

    touched = replace(session, last_seen_at=START_TIME + timedelta(minutes=2))
    repositories.sessions.save(touched)
    assert (
        repositories.sessions.get_by_token_hash(session.token_hash) == touched
    )
    repositories.sessions.save(replace(touched, token_hash="unknown"))
    assert repositories.sessions.get_by_token_hash("unknown") is None

    assert repositories.sessions.delete_by_token_hash(session.token_hash)
    assert not repositories.sessions.delete_by_token_hash(session.token_hash)

    repositories.sessions.add(session)
    repositories.sessions.delete(session.id)
    assert repositories.sessions.get_by_token_hash(session.token_hash) is None


def test_unlock_token_pop_is_one_time(repositories: Repositories) -> None:
    user = new_user()
    repositories.users.add(user)
    token = UnlockToken(
        token_hash="unlock-hash",
        user_id=user.id,
        expires_at=START_TIME + timedelta(minutes=15),
    )
    repositories.unlock_tokens.add(token)
    assert repositories.unlock_tokens.pop(token.token_hash) == token
    assert repositories.unlock_tokens.pop(token.token_hash) is None


def test_access_repository_save_ensure_and_lists(
    repositories: Repositories,
) -> None:
    user = new_user()
    repositories.users.add(user)
    editor = DocumentAccess(document_id=4, user_id=user.id, role=Role.EDITOR)
    guest = replace(editor, role=Role.GUEST)
    other = DocumentAccess(document_id=5, user_id=user.id, role=Role.GUEST)

    repositories.access.save(editor)
    assert repositories.access.get(4, user.id) == editor
    assert repositories.access.ensure(guest) == editor
    repositories.access.save(other)
    assert repositories.access.list_for_document(4) == [editor]
    assert repositories.access.list_for_user(user.id) == [editor, other]

    repositories.access.delete(4, user.id)
    assert repositories.access.get(4, user.id) is None
    assert repositories.access.ensure(guest) == guest


@pytest.mark.parametrize(
    ("decision", "expected_access"),
    [
        (AccessRequestStatus.APPROVED, Role.GUEST),
        (AccessRequestStatus.REJECTED, None),
    ],
)
def test_access_request_transitions_are_atomic_and_one_way(
    repositories: Repositories,
    decision: AccessRequestStatus,
    expected_access: Role | None,
) -> None:
    owner = new_user("owner@example.com")
    requester = new_user("requester@example.com")
    repositories.users.add(owner)
    repositories.users.add(requester)
    repositories.access.save(
        DocumentAccess(document_id=10, user_id=owner.id, role=Role.OWNER)
    )
    request = AccessRequest(
        id=uuid4(),
        document_id=10,
        requester_id=requester.id,
        request_type=AccessRequestType.ACCESS,
        status=AccessRequestStatus.PENDING,
        created_at=START_TIME,
    )
    repositories.access.create_request(request)
    with pytest.raises(AccessRequestAlreadyPendingError):
        repositories.access.create_request(replace(request, id=uuid4()))
    assert repositories.access.list_pending_requests(10) == [request]
    with pytest.raises(AccessDeniedError):
        repositories.access.resolve_request(
            10,
            request.id,
            requester.id,
            decision,
            START_TIME + timedelta(minutes=1),
        )
    assert repositories.access.get_request(10, request.id) == request

    decided = repositories.access.resolve_request(
        10,
        request.id,
        owner.id,
        decision,
        START_TIME + timedelta(minutes=1),
    )
    assert decided.status is decision
    assert decided.resolved_at == START_TIME + timedelta(minutes=1)
    assert repositories.access.list_pending_requests(10) == []
    granted = repositories.access.get(10, requester.id)
    assert (granted.role if granted else None) is expected_access
    with pytest.raises(InvalidAccessRequestTransitionError):
        repositories.access.resolve_request(
            10,
            request.id,
            owner.id,
            (
                AccessRequestStatus.APPROVED
                if decision is AccessRequestStatus.REJECTED
                else AccessRequestStatus.REJECTED
            ),
            START_TIME + timedelta(minutes=2),
        )
    assert repositories.access.list_requests_for_user(requester.id) == [
        decided
    ]


def test_auth_lockout_and_session_timestamps_are_backend_independent(
    repositories: Repositories,
) -> None:
    clock = FakeClock()
    hasher = FakePasswordHasher()
    mail = RecordingEmailSender()
    settings = IamSettings()
    auth = AuthService(
        users=repositories.users,
        sessions=repositories.sessions,
        unlock_tokens=repositories.unlock_tokens,
        hasher=hasher,
        tokens=SecretsTokenGenerator(),
        email_sender=mail,
        clock=clock,
        password_policy=settings.password_policy,
        lockout_policy=settings.lockout_policy,
        session_policy=settings.session_policy,
        unlock_page_url=settings.unlock_page_url,
    )

    registered = auth.register("olena@example.com", VALID_NAME, VALID_PASSWORD)
    for _ in range(settings.lockout_policy.max_failed_attempts):
        with pytest.raises(InvalidCredentialsError):
            auth.login("olena@example.com", "wrong-password")

    locked_user = repositories.users.get_by_id(registered.user.id)
    assert locked_user is not None
    assert locked_user.locked_until == START_TIME + timedelta(minutes=15)
    with pytest.raises(AccountLockedError):
        auth.login("olena@example.com", VALID_PASSWORD)

    clock.advance(minutes=15)
    authenticated = auth.login("olena@example.com", VALID_PASSWORD)
    unlocked_user = repositories.users.get_by_id(registered.user.id)
    assert unlocked_user is not None
    assert unlocked_user.locked_until is None
    assert unlocked_user.failed_login_attempts == 0

    clock.advance(minutes=2)
    auth.verify_session(authenticated.session.access_token)
    stored_session = repositories.sessions.get_by_token_hash(
        hash_token(authenticated.session.access_token)
    )
    assert stored_session is not None
    assert stored_session.last_seen_at == START_TIME + timedelta(minutes=17)
