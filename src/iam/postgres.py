"""PostgreSQL-адаптери IAM для міграцій ``001_iam.sql`` і
``003_access_requests.sql``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from src.iam.errors import (
    AccessDeniedError,
    AccessRequestAlreadyPendingError,
    AccessRequestNotFoundError,
    EmailAlreadyRegisteredError,
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


def _user_from_row(row: dict[str, Any]) -> User:
    return User(
        id=row["id"],
        email=Email(row["email"]),
        name=DisplayName(row["name"]),
        password_hash=row["password_hash"],
        created_at=row["created_at"],
        failed_login_attempts=row["failed_login_attempts"],
        locked_until=row["locked_until"],
    )


def _session_from_row(row: dict[str, Any]) -> Session:
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        token_hash=row["token_hash"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        expires_at=row["expires_at"],
    )


def _unlock_token_from_row(row: dict[str, Any]) -> UnlockToken:
    return UnlockToken(
        token_hash=row["token_hash"],
        user_id=row["user_id"],
        expires_at=row["expires_at"],
    )


def _access_from_row(row: dict[str, Any]) -> DocumentAccess:
    return DocumentAccess(
        document_id=row["document_id"],
        user_id=row["user_id"],
        role=Role(row["role"]),
    )


def _request_from_row(row: dict[str, Any]) -> AccessRequest:
    requested_role = row["requested_role"]
    return AccessRequest(
        id=row["id"],
        document_id=row["document_id"],
        requester_id=row["requester_id"],
        request_type=AccessRequestType(row["request_type"]),
        status=AccessRequestStatus(row["status"]),
        created_at=row["created_at"],
        requested_role=Role(requested_role) if requested_role else None,
        resolved_at=row["resolved_at"],
    )


class PostgresUserRepository:
    """Реалізує ``UserRepository`` на PostgreSQL."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def add(self, user: User) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        id, email, name, password_hash, created_at,
                        failed_login_attempts, locked_until
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user.id,
                        user.email.value,
                        user.name.value,
                        user.password_hash,
                        user.created_at,
                        user.failed_login_attempts,
                        user.locked_until,
                    ),
                )
        except psycopg.errors.UniqueViolation as exc:
            if exc.diag.constraint_name == "users_email_key":
                raise EmailAlreadyRegisteredError(str(user.email)) from exc
            raise

    def get_by_id(self, user_id: UUID) -> User | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = %s", (user_id,)
            ).fetchone()
        return None if row is None else _user_from_row(row)

    def get_by_email(self, email: Email) -> User | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = %s", (email.value,)
            ).fetchone()
        return None if row is None else _user_from_row(row)

    def update(
        self, user_id: UUID, change: Callable[[User], User]
    ) -> User | None:
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM users WHERE id = %s FOR UPDATE",
                    (user_id,),
                ).fetchone()
                if row is None:
                    return None
                current = _user_from_row(row)
                updated = change(current)
                if updated.id != current.id or updated.email != current.email:
                    raise ValueError("update не може змінювати id або email.")
                conn.execute(
                    """
                    UPDATE users
                    SET name = %s, password_hash = %s,
                        created_at = %s, failed_login_attempts = %s,
                        locked_until = %s
                    WHERE id = %s
                    """,
                    (
                        updated.name.value,
                        updated.password_hash,
                        updated.created_at,
                        updated.failed_login_attempts,
                        updated.locked_until,
                        user_id,
                    ),
                )
        return updated


class PostgresSessionRepository:
    """Реалізує ``SessionRepository``; пошук ведеться за хешем токена."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def add(self, session: Session) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, user_id, token_hash, created_at, last_seen_at,
                    expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session.id,
                    session.user_id,
                    session.token_hash,
                    session.created_at,
                    session.last_seen_at,
                    session.expires_at,
                ),
            )

    def get_by_token_hash(self, token_hash: str) -> Session | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = %s",
                (token_hash,),
            ).fetchone()
        return None if row is None else _session_from_row(row)

    def save(self, session: Session) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET user_id = %s, created_at = %s, last_seen_at = %s,
                    expires_at = %s
                WHERE token_hash = %s
                """,
                (
                    session.user_id,
                    session.created_at,
                    session.last_seen_at,
                    session.expires_at,
                    session.token_hash,
                ),
            )

    def delete(self, session_id: UUID) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE id = %s", (session_id,))

    def delete_by_token_hash(self, token_hash: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "DELETE FROM sessions WHERE token_hash = %s RETURNING id",
                (token_hash,),
            ).fetchone()
        return row is not None


class PostgresUnlockTokenRepository:
    """Реалізує одноразове сховище токенів розблокування."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def add(self, token: UnlockToken) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO unlock_tokens (token_hash, user_id, expires_at)
                VALUES (%s, %s, %s)
                """,
                (token.token_hash, token.user_id, token.expires_at),
            )

    def pop(self, token_hash: str) -> UnlockToken | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                DELETE FROM unlock_tokens
                WHERE token_hash = %s
                RETURNING token_hash, user_id, expires_at
                """,
                (token_hash,),
            ).fetchone()
        return None if row is None else _unlock_token_from_row(row)


class PostgresAccessRepository:
    """Реалізує ``AccessRepository`` для ролей у документах."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get(self, document_id: int, user_id: UUID) -> DocumentAccess | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT document_id, user_id, role
                FROM document_access
                WHERE document_id = %s AND user_id = %s
                """,
                (document_id, user_id),
            ).fetchone()
        return None if row is None else _access_from_row(row)

    def save(self, access: DocumentAccess) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO document_access (document_id, user_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (document_id, user_id)
                DO UPDATE SET role = EXCLUDED.role
                """,
                (access.document_id, access.user_id, access.role.value),
            )

    def ensure(self, access: DocumentAccess) -> DocumentAccess:
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    INSERT INTO document_access (document_id, user_id, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (document_id, user_id) DO NOTHING
                    RETURNING document_id, user_id, role
                    """,
                    (access.document_id, access.user_id, access.role.value),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        """
                        SELECT document_id, user_id, role
                        FROM document_access
                        WHERE document_id = %s AND user_id = %s
                        """,
                        (access.document_id, access.user_id),
                    ).fetchone()
                if row is None:
                    raise RuntimeError(
                        "Не вдалося прочитати збережений доступ до документа."
                    )
        return _access_from_row(row)

    def delete(self, document_id: int, user_id: UUID) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                DELETE FROM document_access
                WHERE document_id = %s AND user_id = %s
                """,
                (document_id, user_id),
            )

    def list_for_document(self, document_id: int) -> list[DocumentAccess]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT document_id, user_id, role
                FROM document_access
                WHERE document_id = %s
                ORDER BY user_id
                """,
                (document_id,),
            ).fetchall()
        return [_access_from_row(row) for row in rows]

    def list_for_user(self, user_id: UUID) -> list[DocumentAccess]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT document_id, user_id, role
                FROM document_access
                WHERE user_id = %s
                ORDER BY document_id
                """,
                (user_id,),
            ).fetchall()
        return [_access_from_row(row) for row in rows]

    def create_request(self, request: AccessRequest) -> AccessRequest:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO access_requests (
                        id, document_id, requester_id, request_type,
                        requested_role, status, created_at, resolved_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        request.id,
                        request.document_id,
                        request.requester_id,
                        request.request_type.value,
                        (
                            request.requested_role.value
                            if request.requested_role
                            else None
                        ),
                        request.status.value,
                        request.created_at,
                        request.resolved_at,
                    ),
                )
        except psycopg.errors.UniqueViolation as exc:
            if (
                exc.diag.constraint_name
                == "access_requests_one_pending_per_type"
            ):
                raise AccessRequestAlreadyPendingError() from exc
            raise
        return request

    def get_request(
        self, document_id: int, request_id: UUID
    ) -> AccessRequest | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM access_requests
                WHERE document_id = %s AND id = %s
                """,
                (document_id, request_id),
            ).fetchone()
        return None if row is None else _request_from_row(row)

    def list_pending_requests(self, document_id: int) -> list[AccessRequest]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM access_requests
                WHERE document_id = %s AND status = 'pending'
                ORDER BY created_at, id
                """,
                (document_id,),
            ).fetchall()
        return [_request_from_row(row) for row in rows]

    def list_requests_for_user(self, user_id: UUID) -> list[AccessRequest]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM access_requests
                WHERE requester_id = %s
                ORDER BY created_at DESC, id
                """,
                (user_id,),
            ).fetchall()
        return [_request_from_row(row) for row in rows]

    def resolve_request(
        self,
        document_id: int,
        request_id: UUID,
        reviewer_id: UUID,
        status: AccessRequestStatus,
        now: datetime,
    ) -> AccessRequest:
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    SELECT *
                    FROM access_requests
                    WHERE document_id = %s AND id = %s
                    FOR UPDATE
                    """,
                    (document_id, request_id),
                ).fetchone()
                if row is None:
                    raise AccessRequestNotFoundError()

                owner = conn.execute(
                    """
                    SELECT 1
                    FROM document_access
                    WHERE document_id = %s AND user_id = %s AND role = 'owner'
                    """,
                    (document_id, reviewer_id),
                ).fetchone()
                if owner is None:
                    raise AccessDeniedError()

                request = _request_from_row(row)
                resolved = request.decide(status, now)
                if status is AccessRequestStatus.APPROVED:
                    role = request.requested_role or Role.GUEST
                    conn.execute(
                        """
                        INSERT INTO document_access (
                            document_id, user_id, role
                        ) VALUES (%s, %s, %s)
                        ON CONFLICT (document_id, user_id)
                        DO NOTHING
                        """,
                        (document_id, request.requester_id, role.value),
                    )
                conn.execute(
                    """
                    UPDATE access_requests
                    SET status = %s, resolved_at = %s
                    WHERE id = %s
                    """,
                    (status.value, now, request_id),
                )
        return resolved
