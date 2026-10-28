"""HTTP routes for calendar events and participants."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.responses import JSONResponse

from src.api.common import (
    AUTH_ERROR_RESPONSES,
    VALIDATION_ERROR_RESPONSE,
    ApiError,
    error_response,
)
from src.api.security import require_user
from src.calendar_events.models import Event
from src.calendar_events.service import (
    CalendarAccessDeniedError,
    CalendarService,
    EventNotFoundError,
    InvalidEventError,
)
from src.iam import UserView
from src.iam.errors import InvalidEmailError
from src.iam.models import Email

router = APIRouter(prefix="/calendar/events", tags=["calendar"])

EventId = Annotated[
    int, Path(gt=0, description="Додатний ідентифікатор події.")
]


class EventCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> EventCreate:
        _require_aware(self.start_at)
        _require_aware(self.end_at)
        if self.end_at <= self.start_at:
            raise ValueError("Час завершення має бути пізніше за час початку.")
        return self


class EventUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=100)
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_update(self) -> EventUpdate:
        if (
            self.title is None
            and self.start_at is None
            and self.end_at is None
        ):
            raise ValueError("Потрібно вказати хоча б одне поле для зміни.")
        if self.start_at is not None:
            _require_aware(self.start_at)
        if self.end_at is not None:
            _require_aware(self.end_at)
        return self


class ParticipantAdd(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=254)

    @model_validator(mode="after")
    def normalize_email(self) -> ParticipantAdd:
        try:
            normalized = Email.parse(self.email)
        except InvalidEmailError as exc:
            raise ValueError("Некоректна email-адреса.") from exc
        return self.model_copy(update={"email": normalized.value})


class DocumentLink(BaseModel):
    document_id: int = Field(gt=0)


class EventResponse(BaseModel):
    id: int
    creator_id: UUID
    title: str
    start_at: datetime
    end_at: datetime
    document_id: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_event(cls, event: Event) -> EventResponse:
        return cls(
            id=event.id,
            creator_id=event.creator_id,
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
            document_id=event.document_id,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Дата й час мають містити часовий пояс.")


def get_calendar_service(request: Request) -> CalendarService:
    return request.app.state.calendar.service


CurrentUser = Annotated[UserView, Depends(require_user)]
Calendar = Annotated[CalendarService, Depends(get_calendar_service)]

CALENDAR_ERROR_RESPONSES = {
    **AUTH_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: error_response(
        "Подію або користувача не знайдено.",
        "Подію не знайдено.",
    ),
    status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
}


def register_calendar_error_handlers(app: FastAPI) -> None:
    async def handle_not_found(
        _request: Request, exc: EventNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ApiError(detail=str(exc)).model_dump(),
        )

    async def handle_forbidden(
        _request: Request, _exc: CalendarAccessDeniedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=ApiError(
                detail="Недостатньо прав для цієї дії."
            ).model_dump(),
        )

    async def handle_invalid(
        _request: Request, exc: InvalidEventError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ApiError(detail=str(exc)).model_dump(),
        )

    app.add_exception_handler(EventNotFoundError, handle_not_found)
    app.add_exception_handler(CalendarAccessDeniedError, handle_forbidden)
    app.add_exception_handler(InvalidEventError, handle_invalid)


@router.get(
    "",
    response_model=list[EventResponse],
    summary="Список подій у часовому діапазоні",
    responses=CALENDAR_ERROR_RESPONSES,
)
def list_events(
    user: CurrentUser,
    service: Calendar,
    start_at: Annotated[datetime, Query()],
    end_at: Annotated[datetime, Query()],
) -> list[EventResponse]:
    try:
        _require_aware(start_at)
        _require_aware(end_at)
    except ValueError as exc:
        raise InvalidEventError(str(exc)) from exc
    if end_at <= start_at:
        raise InvalidEventError(
            "Час завершення має бути пізніше за час початку."
        )
    events = service.list_in_range(user.id, start_at, end_at)
    return [EventResponse.from_event(event) for event in events]


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Створити подію",
    responses=CALENDAR_ERROR_RESPONSES,
)
def create_event(
    payload: EventCreate, user: CurrentUser, service: Calendar
) -> EventResponse:
    event = service.create_event(
        user.id, payload.title, payload.start_at, payload.end_at
    )
    return EventResponse.from_event(event)


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Отримати подію",
    responses=CALENDAR_ERROR_RESPONSES,
)
def read_event(
    event_id: EventId, user: CurrentUser, service: Calendar
) -> EventResponse:
    return EventResponse.from_event(service.get_event(event_id, user.id))


@router.patch(
    "/{event_id}",
    response_model=EventResponse,
    summary="Змінити подію",
    responses=CALENDAR_ERROR_RESPONSES,
)
def update_event(
    event_id: EventId,
    payload: EventUpdate,
    user: CurrentUser,
    service: Calendar,
) -> EventResponse:
    event = service.update_event(
        event_id,
        user.id,
        title=payload.title,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )
    return EventResponse.from_event(event)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалити подію",
    responses=CALENDAR_ERROR_RESPONSES,
)
def delete_event(
    event_id: EventId, user: CurrentUser, service: Calendar
) -> None:
    service.delete_event(event_id, user.id)


@router.get(
    "/{event_id}/participants",
    response_model=list[UUID],
    summary="Список учасників події",
    responses=CALENDAR_ERROR_RESPONSES,
)
def list_participants(
    event_id: EventId, user: CurrentUser, service: Calendar
) -> list[UUID]:
    return service.list_participants(event_id, user.id)


@router.put(
    "/{event_id}/participants",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Додати учасника за email",
    responses=CALENDAR_ERROR_RESPONSES,
)
def add_participant(
    event_id: EventId,
    payload: ParticipantAdd,
    user: CurrentUser,
    service: Calendar,
) -> None:
    service.add_participant_by_email(event_id, user.id, payload.email)


@router.delete(
    "/{event_id}/participants/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Вийти з події",
    responses=CALENDAR_ERROR_RESPONSES,
)
def leave_event(
    event_id: EventId, user: CurrentUser, service: Calendar
) -> None:
    service.remove_self(event_id, user.id)


@router.delete(
    "/{event_id}/participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалити учасника",
    responses=CALENDAR_ERROR_RESPONSES,
)
def remove_participant(
    event_id: EventId,
    participant_id: UUID,
    user: CurrentUser,
    service: Calendar,
) -> None:
    service.remove_participant(event_id, user.id, participant_id)


@router.put(
    "/{event_id}/document",
    response_model=EventResponse,
    summary="Прив'язати документ",
    responses=CALENDAR_ERROR_RESPONSES,
)
def link_document(
    event_id: EventId,
    payload: DocumentLink,
    user: CurrentUser,
    service: Calendar,
) -> EventResponse:
    return EventResponse.from_event(
        service.link_document(event_id, user.id, payload.document_id)
    )


@router.delete(
    "/{event_id}/document",
    response_model=EventResponse,
    summary="Відв'язати документ",
    responses=CALENDAR_ERROR_RESPONSES,
)
def unlink_document(
    event_id: EventId, user: CurrentUser, service: Calendar
) -> EventResponse:
    return EventResponse.from_event(service.unlink_document(event_id, user.id))


# File was created by Copilot and reviewed by Olha Marushchenko
