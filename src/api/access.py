"""Маршрути керування доступом до документа (FR-040–FR-043, I-05).

Тонкий HTTP-адаптер до ``AccessService``: усі правила (хто може
ділитися, кому не можна змінювати роль) — у ``src/iam/access.py``.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, Field

from src.api.auth.errors import ACCESS_DENIED_DETAIL
from src.api.common import (
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    error_response,
)
from src.api.security import get_access, require_user
from src.iam import AccessService, Member, Role, UserView

router = APIRouter(prefix="/documents/{document_id}/access", tags=["access"])

DocumentId = Annotated[
    int, Path(gt=0, description="Додатний ідентифікатор документа.")
]

FORBIDDEN_RESPONSE = error_response(
    "Керувати доступом може лише власник документа.", ACCESS_DENIED_DETAIL
)


class ShareRequest(BaseModel):
    """Кому і з якою роллю надати доступ."""

    email: str = Field(max_length=254, examples=["andrii@example.com"])
    role: Literal["editor", "guest"] = Field(
        description="editor — може редагувати, guest — лише переглядати."
    )


class MemberResponse(BaseModel):
    """Учасник документа."""

    user_id: UUID
    email: str
    name: str
    role: Role

    @classmethod
    def from_member(cls, member: Member) -> MemberResponse:
        return cls(
            user_id=member.user.id,
            email=member.user.email,
            name=member.user.name,
            role=member.role,
        )


class MembersResponse(BaseModel):
    """Усі учасники документа, включно з власником."""

    members: list[MemberResponse]


@router.get(
    "",
    response_model=MembersResponse,
    summary="Учасники документа",
    description="Повертає список учасників і їхні ролі. Лише для власника.",
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: FORBIDDEN_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def list_members(
    document_id: DocumentId,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> MembersResponse:
    members = access.members(user.id, document_id)
    return MembersResponse(
        members=[MemberResponse.from_member(member) for member in members]
    )


@router.put(
    "",
    response_model=MemberResponse,
    summary="Поділитися документом або змінити роль",
    description=(
        "Надає зареєстрованому користувачу роль editor або guest (FR-040). "
        "Повторний виклик для того самого email змінює роль (FR-043). "
        "Лише для власника (FR-057)."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: FORBIDDEN_RESPONSE,
        status.HTTP_404_NOT_FOUND: error_response(
            "Користувача з таким email не зареєстровано.",
            "Користувача з таким email не знайдено.",
        ),
        status.HTTP_409_CONFLICT: error_response(
            "Спроба змінити роль власника.",
            "Роль власника документа змінити не можна.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def share_document(
    document_id: DocumentId,
    payload: ShareRequest,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> MemberResponse:
    member = access.share(
        user.id, document_id, payload.email, Role(payload.role)
    )
    return MemberResponse.from_member(member)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Забрати доступ",
    description="Видаляє користувача з документа (FR-042). Лише власник.",
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: FORBIDDEN_RESPONSE,
        status.HTTP_409_CONFLICT: error_response(
            "Спроба забрати доступ у власника.",
            "Роль власника документа змінити не можна.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def revoke_access(
    document_id: DocumentId,
    user_id: UUID,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> None:
    access.revoke(user.id, document_id, user_id)


# File was created by Claude. Reviewed by Kozynska Anastasia
