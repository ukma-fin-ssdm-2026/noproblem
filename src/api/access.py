"""Маршрути керування доступом до документа (FR-040–FR-043, I-05).

Тонкий HTTP-адаптер до ``AccessService``: усі правила (хто може
ділитися, кому не можна змінювати роль) — у ``src/iam/access.py``.
"""

from __future__ import annotations

from datetime import datetime
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
from src.documents.models import AccessMode
from src.iam import AccessService, Member, Role, UserView
from src.iam.models import (
    AccessRequest,
    AccessRequestStatus,
    AccessRequestType,
)

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


class AccessModeRequest(BaseModel):
    """Режим доступу документа."""

    mode: AccessMode


class AccessModeResponse(BaseModel):
    """Поточний режим доступу документа."""

    mode: AccessMode


class AccessRequestResponse(BaseModel):
    """Запит на доступ або зміну ролі."""

    id: UUID
    document_id: int
    requester_id: UUID
    request_type: AccessRequestType
    requested_role: Role | None
    status: AccessRequestStatus
    created_at: datetime
    resolved_at: datetime | None

    @classmethod
    def from_request(cls, request: AccessRequest) -> AccessRequestResponse:
        return cls(
            id=request.id,
            document_id=request.document_id,
            requester_id=request.requester_id,
            request_type=request.request_type,
            requested_role=request.requested_role,
            status=request.status,
            created_at=request.created_at,
            resolved_at=request.resolved_at,
        )


class AccessRequestsResponse(BaseModel):
    """Список запитів."""

    requests: list[AccessRequestResponse]

    @classmethod
    def from_requests(
        cls, requests: list[AccessRequest]
    ) -> AccessRequestsResponse:
        return cls(
            requests=[
                AccessRequestResponse.from_request(request)
                for request in requests
            ]
        )


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
    "/mode",
    response_model=AccessModeResponse,
    summary="Змінити режим доступу",
    description=(
        "Перемикає документ між обмеженим доступом і доступом за "
        "посиланням. Лише для власника (FR-044, FR-045). У режимі за "
        "посиланням автентифікований користувач отримує роль Guest під "
        "час першого доступу до документа (FR-052)."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: FORBIDDEN_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def change_access_mode(
    document_id: DocumentId,
    payload: AccessModeRequest,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> AccessModeResponse:
    document = access.change_access_mode(user.id, document_id, payload.mode)
    return AccessModeResponse(mode=document.access_mode)


@router.post(
    "/requests",
    response_model=AccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Надіслати запит на доступ",
    description=(
        "Надсилає власнику запит на доступ до документа з обмеженим "
        "режимом (FR-046, FR-047). Поки запит очікує, повторне надсилання "
        "повертає 409 (FR-051)."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: error_response(
            "Документ недоступний для запиту.",
            ACCESS_DENIED_DETAIL,
        ),
        status.HTTP_409_CONFLICT: error_response(
            "Запит уже очікує або не потрібен.",
            "Запит на доступ до цього документа вже очікує на розгляд.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def request_document_access(
    document_id: DocumentId,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> AccessRequestResponse:
    request = access.request_access(user.id, document_id)
    return AccessRequestResponse.from_request(request)


@router.get(
    "/requests",
    response_model=AccessRequestsResponse,
    summary="Очікувані запити на доступ",
    description="Повертає запити, що очікують розгляду. Лише для Owner.",
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: FORBIDDEN_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def list_access_requests(
    document_id: DocumentId,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> AccessRequestsResponse:
    requests = access.pending_access_requests(user.id, document_id)
    return AccessRequestsResponse.from_requests(requests)


@router.get(
    "/requests/mine",
    response_model=AccessRequestsResponse,
    summary="Мої запити на доступ",
    description=(
        "Повертає запити поточного користувача та їхній статус, зокрема "
        "повідомлення про відхилення (FR-050)."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def list_my_access_requests(
    document_id: DocumentId,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> AccessRequestsResponse:
    requests = access.requests_for_user(user.id, document_id)
    return AccessRequestsResponse.from_requests(requests)


def _review_request(
    document_id: int,
    request_id: UUID,
    user: UserView,
    access: AccessService,
    *,
    approve: bool,
) -> AccessRequestResponse:
    request = access.review_access_request(
        user.id, document_id, request_id, approve=approve
    )
    return AccessRequestResponse.from_request(request)


@router.post(
    "/requests/{request_id}/approve",
    response_model=AccessRequestResponse,
    summary="Підтвердити запит на доступ",
    description=(
        "Підтверджує запит, надаючи користувачу роль Guest (FR-049). "
        "Лише для Owner."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: FORBIDDEN_RESPONSE,
        status.HTTP_404_NOT_FOUND: error_response(
            "Запит не знайдено.", "Запит на доступ не знайдено."
        ),
        status.HTTP_409_CONFLICT: error_response(
            "Запит уже розглянуто.",
            "Запит уже розглянуто й не може бути змінений повторно.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def approve_access_request(
    document_id: DocumentId,
    request_id: UUID,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> AccessRequestResponse:
    return _review_request(document_id, request_id, user, access, approve=True)


@router.post(
    "/requests/{request_id}/reject",
    response_model=AccessRequestResponse,
    summary="Відхилити запит на доступ",
    description=(
        "Відхиляє запит, не надаючи доступу. Статус буде доступний "
        "користувачу в його списку запитів (FR-050). Лише для Owner."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED_RESPONSE,
        status.HTTP_403_FORBIDDEN: FORBIDDEN_RESPONSE,
        status.HTTP_404_NOT_FOUND: error_response(
            "Запит не знайдено.", "Запит на доступ не знайдено."
        ),
        status.HTTP_409_CONFLICT: error_response(
            "Запит уже розглянуто.",
            "Запит уже розглянуто й не може бути змінений повторно.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
    },
)
def reject_access_request(
    document_id: DocumentId,
    request_id: UUID,
    user: UserView = Depends(require_user),
    access: AccessService = Depends(get_access),
) -> AccessRequestResponse:
    return _review_request(
        document_id, request_id, user, access, approve=False
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
