"""Доступ до документів: ролі Owner / Editor / Guest (FR-040–FR-043, FR-057).

``AuthService`` відповідає на питання «хто ти?», а ``AccessService`` — на
питання «що тобі можна з цим документом?». Інші компоненти (документи,
у майбутньому Collab, Search, Calendar) викликають ``check`` перед
кожною операцією (інтерфейси I-09, I-11–I-13).

Відкладено на наступні етапи: режим «За посиланням», запити на доступ і
запрошення незареєстрованих користувачів (FR-044–FR-056, FR-007).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from src.iam.errors import (
    AccessDeniedError,
    OwnerAccessChangeError,
    UserNotFoundError,
)
from src.iam.models import Action, DocumentAccess, Role
from src.iam.ports import AccessRepository
from src.iam.service import AuthService, UserView, security_log


@dataclass(frozen=True)
class Member:
    """Учасник документа: хто і з якою роллю."""

    user: UserView
    role: Role


class AccessService:
    """Ролі в документах і перевірка прав."""

    def __init__(self, *, access: AccessRepository, auth: AuthService):
        self._access = access
        self._auth = auth

    # -- Перевірка прав ----------------------------------------------------

    def has_permission(
        self, user_id: UUID, document_id: int, action: Action
    ) -> bool:
        """Чи може користувач виконати дію (без запису в журнал)."""
        access = self._access.get(document_id, user_id)
        return access is not None and access.allows(action)

    def check(self, user_id: UUID, document_id: int, action: Action) -> None:
        """Пропускає дію або кидає ``AccessDeniedError`` (403).

        Кожна відмова записується в журнал безпеки (сценарій S-SEC-002).

        Raises:
            AccessDeniedError: Немає ролі, що дозволяє цю дію.
        """
        if not self.has_permission(user_id, document_id, action):
            security_log.warning(
                "access_denied user_id=%s document_id=%s action=%s",
                user_id,
                document_id,
                action.value,
            )
            raise AccessDeniedError()

    def accessible_document_ids(self, user_id: UUID) -> set[int]:
        """Документи, які користувач може переглядати (для списків)."""
        return {
            access.document_id
            for access in self._access.list_for_user(user_id)
            if access.allows(Action.VIEW)
        }

    # GREEN test: Guest can see member count without listing members (FR-043) 
    # Made with Copilot
    def member_count(self, user_id: UUID, document_id: int) -> int:
        """Кількість учасників документа для користувача з правом перегляду."""
        self.check(user_id, document_id, Action.VIEW)
        return len(self._access.list_for_document(document_id))

    # -- Керування доступом ------------------------------------------------

    def grant_owner(self, document_id: int, user_id: UUID) -> None:
        """Робить автора нового документа його власником (FR-008)."""
        self._access.save(DocumentAccess(document_id, user_id, Role.OWNER))

    def share(
        self, owner_id: UUID, document_id: int, email: str, role: Role
    ) -> Member:
        """Додає користувача за email або змінює його роль (FR-040, FR-043).

        Raises:
            AccessDeniedError: Діє не власник (FR-057, NFR-SEC-004).
            UserNotFoundError: Email не зареєстровано.
            OwnerAccessChangeError: Спроба змінити роль власника або
                призначити ще одного власника.
        """
        self.check(owner_id, document_id, Action.MANAGE_ACCESS)
        if role is Role.OWNER:
            raise OwnerAccessChangeError()
        user = self._auth.find_user_by_email(email)
        if user is None:
            raise UserNotFoundError()
        current = self._access.get(document_id, user.id)
        if current is not None and current.role is Role.OWNER:
            raise OwnerAccessChangeError()
        self._access.save(DocumentAccess(document_id, user.id, role))
        security_log.info(
            "access_granted document_id=%s user_id=%s role=%s",
            document_id,
            user.id,
            role.value,
        )
        return Member(user=user, role=role)

    def revoke(self, owner_id: UUID, document_id: int, user_id: UUID) -> None:
        """Забирає доступ у користувача (FR-042).

        Raises:
            AccessDeniedError: Діє не власник.
            OwnerAccessChangeError: Спроба забрати доступ у власника.
        """
        self.check(owner_id, document_id, Action.MANAGE_ACCESS)
        current = self._access.get(document_id, user_id)
        if current is not None and current.role is Role.OWNER:
            raise OwnerAccessChangeError()
        self._access.delete(document_id, user_id)
        security_log.info(
            "access_revoked document_id=%s user_id=%s", document_id, user_id
        )

    def members(self, requester_id: UUID, document_id: int) -> list[Member]:
        """Список учасників документа; бачить лише власник."""
        self.check(requester_id, document_id, Action.MANAGE_ACCESS)
        result = []
        for access in self._access.list_for_document(document_id):
            user = self._auth.get_user(access.user_id)
            if user is not None:
                result.append(Member(user=user, role=access.role))
        return result


# File was created by Claude. Reviewed by Kozynska Anastasia
