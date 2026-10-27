"""HTTP-маршрути документів, кошика й абзаців (інтерфейс I-06).

Тонкий адаптер до ``DocumentService``: перетворює HTTP-запит на виклик
сервісу, доменні об'єкти — на JSON, а доменні винятки — на 404/409/422.
Уся логіка (права, кошик, ідемпотентність, позиції абзаців) — у
``src/documents``. Описи маршрутів і моделей перенесено з ``main.py``
без змін, тож специфікація OpenAPI та сама.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    Path,
    Query,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api import metrics
from src.api.common import (
    AUTH_ERROR_RESPONSES,
    VALIDATION_ERROR_RESPONSE,
    ApiError,
)
from src.api.security import require_user
from src.documents.errors import (
    DocumentNotFoundError,
    DocumentNotInTrashError,
    DocumentsError,
    IdempotencyConflictError,
    InsertPositionError,
    MovePositionError,
    ParagraphNotFoundError,
)
from src.documents.models import Document, Paragraph
from src.documents.service import DocumentService
from src.iam import UserView


class AccessMode(str, Enum):
    restricted = "restricted"
    link = "link"


class DocumentCreate(BaseModel):
    """Поля для створення документа."""

    model_config = ConfigDict(str_strip_whitespace=True)
    title: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Назва документа. Якщо її не вказано, використовується «Без "
            "назви»."
        ),
        examples=["План проєкту"],
    )


class DocumentUpdate(BaseModel):
    """Поля для перейменування документа."""

    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(
        min_length=1,
        max_length=100,
        description="Нова назва документа: від 1 до 100 символів.",
        examples=["Оновлений план проєкту"],
    )


class DocumentResponse(BaseModel):
    """Документ, що повертається API."""

    id: int = Field(
        description="Унікальний ідентифікатор документа.", examples=[1]
    )
    title: str = Field(
        description="Назва документа.", examples=["Нотатки команди"]
    )
    access_mode: AccessMode = Field(description="Режим доступу до документа.")
    created_at: datetime = Field(description="Час створення документа в UTC.")
    updated_at: datetime = Field(
        description="Час останньої зміни документа в UTC."
    )
    deleted_at: datetime | None = Field(
        default=None,
        description=(
            "Час переміщення документа до кошика; null для активного "
            "документа."
        ),
    )


MAX_PARAGRAPH_LENGTH = 10_000


class ParagraphCreate(BaseModel):
    """Поля для додавання абзацу в кінець документа або у вказану позицію."""

    content: str = Field(
        ...,
        max_length=MAX_PARAGRAPH_LENGTH,
        description=(
            "Текст абзацу (до 10 000 символів). "
            "Порожній текст дозволений для порожнього абзацу."
        ),
        examples=["Текст першого абзацу"],
    )
    position: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Нульова позиція вставлення; якщо не вказано, абзац додається в "
            "кінець."
        ),
        examples=[0],
    )


class ParagraphUpdate(BaseModel):
    """Поля для зміни вмісту та/або позиції абзацу."""

    content: str | None = Field(
        default=None,
        max_length=MAX_PARAGRAPH_LENGTH,
        description=(
            "Новий текст абзацу; null або "
            "пропуск залишає текст без змін. Максимум 10 000 символів."
        ),
        examples=["Оновлений текст абзацу"],
    )
    position: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Нова нульова позиція абзацу; позиції поза документом "
            "відхиляються."
        ),
        examples=[1],
    )

    @model_validator(mode="after")
    def require_an_update(self) -> "ParagraphUpdate":
        if self.content is None and self.position is None:
            raise ValueError(
                "Потрібно вказати новий вміст або нову позицію абзацу."
            )
        return self


class ParagraphResponse(BaseModel):
    """Абзац документа."""

    id: int = Field(
        description="Унікальний ідентифікатор абзацу.", examples=[1]
    )
    document_id: int = Field(
        description="Ідентифікатор документа-власника.", examples=[1]
    )
    position: int = Field(
        ge=0, description="Позиція абзацу, починаючи з нуля.", examples=[0]
    )
    content: str = Field(
        description="Текст абзацу.", examples=["Текст документа"]
    )


class PaginationInfo(BaseModel):
    """Метадані пагінації списку."""

    limit: int = Field(
        ge=1,
        le=100,
        description="Максимальна кількість елементів у відповіді.",
    )
    offset: int = Field(ge=0, description="Кількість пропущених елементів.")
    total: int = Field(ge=0, description="Загальна кількість елементів.")
    has_more: bool = Field(description="Чи є елементи на наступній сторінці.")


class DocumentsResponse(BaseModel):
    """Сторінка активних документів."""

    documents: list[DocumentResponse] = Field(
        description="Документи на поточній сторінці."
    )
    pagination: PaginationInfo = Field(description="Метадані пагінації.")


class TrashResponse(BaseModel):
    """Сторінка документів у кошику."""

    documents: list[DocumentResponse] = Field(
        description="Документи в кошику на поточній сторінці."
    )
    pagination: PaginationInfo = Field(description="Метадані пагінації.")


class ParagraphsResponse(BaseModel):
    """Список абзаців документа у порядку відображення."""

    paragraphs: list[ParagraphResponse] = Field(
        description="Абзаци документа."
    )


COMMON_ERROR_RESPONSES = {
    **AUTH_ERROR_RESPONSES,
    status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
}

RESOURCE_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ApiError,
        "description": (
            "Документ або абзац не знайдено, або ресурс не перебуває "
            "в очікуваному стані."
        ),
        "content": {
            "application/json": {
                "example": {"detail": "Документ не знайдено."}
            }
        },
    },
}

DOCUMENT_PATH_ID = Path(
    gt=0,
    description="Додатний ідентифікатор документа.",
    examples=[1],
)
# Автентифікований користувач: FastAPI бере його з токена через Шлюз
# (src/api/security.py); без дійсного токена маршрут поверне 401.
CurrentUser = Annotated[UserView, Depends(require_user)]

PARAGRAPH_PATH_ID = Path(
    gt=0,
    description="Додатний ідентифікатор абзацу.",
    examples=[1],
)


def pagination_info(limit: int, offset: int, total: int) -> PaginationInfo:
    return PaginationInfo(
        limit=limit,
        offset=offset,
        total=total,
        has_more=offset + limit < total,
    )


def get_document_service(request: Request) -> DocumentService:
    """Сервіс документів, створений у ``create_app``."""
    return request.app.state.documents.service


Documents = Annotated[DocumentService, Depends(get_document_service)]


def document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        title=document.title,
        access_mode=AccessMode(document.access_mode.value),
        created_at=document.created_at,
        updated_at=document.updated_at,
        deleted_at=document.deleted_at,
    )


def paragraph_response(paragraph: Paragraph) -> ParagraphResponse:
    return ParagraphResponse(
        id=paragraph.id,
        document_id=paragraph.document_id,
        position=paragraph.position,
        content=paragraph.content,
    )


def document_error_detail(exc: DocumentsError) -> tuple[int, str]:
    """Статус і текст відповіді для доменного винятку документів.

    Тексти ті самі, що повертав ``main.py`` до винесення модуля.

    Raises:
        DocumentsError: Для винятку немає запису — передається далі й
            стає 500, а не мовчки отримує випадковий код.
    """
    if isinstance(exc, DocumentNotFoundError):
        return (
            status.HTTP_404_NOT_FOUND,
            f"Активний документ з id={exc.document_id} не знайдено.",
        )
    if isinstance(exc, DocumentNotInTrashError):
        return (
            status.HTTP_404_NOT_FOUND,
            f"Документ з id={exc.document_id} не знайдено в кошику.",
        )
    if isinstance(exc, ParagraphNotFoundError):
        return (
            status.HTTP_404_NOT_FOUND,
            f"Абзац з id={exc.paragraph_id} не знайдено в документі "
            f"{exc.document_id}.",
        )
    if isinstance(exc, IdempotencyConflictError):
        return (
            status.HTTP_409_CONFLICT,
            "Idempotency-Key вже використаний з іншою назвою документа.",
        )
    if isinstance(exc, InsertPositionError):
        return (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Позиція вставлення не може бути більшою за кількість абзаців.",
        )
    if isinstance(exc, MovePositionError):
        return (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Нова позиція має бути в межах наявних позицій абзаців.",
        )
    raise exc


def register_document_error_handlers(app: FastAPI) -> None:
    """Підключає обробник доменних винятків документів до застосунку."""

    async def handle_document_error(
        _request: Request, exc: DocumentsError
    ) -> JSONResponse:
        status_code, detail = document_error_detail(exc)
        return JSONResponse(
            status_code=status_code,
            content=ApiError(detail=detail).model_dump(),
        )

    app.add_exception_handler(DocumentsError, handle_document_error)


router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Створити документ",
    description=(
        "Створює документ з обмеженим доступом. Заголовок "
        "Idempotency-Key обов'язковий. "
        "Повтор із тим самим ключем і тією самою назвою повертає той "
        "самий документ "
        "зі статусом 201; повторне використання ключа з іншою назвою "
        "повертає 409."
    ),
    response_description=(
        "Створений документ або результат повтору ідемпотентного запиту."
    ),
    responses={
        status.HTTP_201_CREATED: {
            "description": (
                "Документ створено або повернено результат попереднього "
                "запиту."
            )
        },
        status.HTTP_409_CONFLICT: {
            "model": ApiError,
            "description": (
                "Ключ ідемпотентності вже використаний з іншим вмістом "
                "запиту."
            ),
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "Idempotency-Key вже використаний з іншою "
                            "назвою документа."
                        )
                    }
                }
            },
        },
        **COMMON_ERROR_RESPONSES,
    },
)
def create_document(
    service: Documents,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            description=(
                "Унікальний ключ для безпечного повтору запиту створення."
            ),
            examples=["create-document-request-001"],
        ),
    ],
    user: CurrentUser,
    payload: DocumentCreate | None = None,
) -> DocumentResponse:
    title = payload.title if payload else None
    outcome = service.create(user.id, idempotency_key, title)
    if not outcome.created:
        metrics.IDEMPOTENT_REPLAYS.inc()
    return document_response(outcome.document)


@router.get(
    "/documents",
    response_model=DocumentsResponse,
    summary="Отримати список активних документів",
    description=(
        "Повертає сторінку активних документів; документи з кошика не "
        "включаються."
    ),
    response_description="Документи та метадані пагінації.",
    responses={
        status.HTTP_200_OK: {"description": "Список документів отримано."},
        **COMMON_ERROR_RESPONSES,
    },
)
def list_documents(
    service: Documents,
    user: CurrentUser,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Максимальна кількість документів у відповіді.",
            examples=[20],
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description=(
                "Кількість активних документів, які потрібно пропустити."
            ),
            examples=[0],
        ),
    ] = 0,
) -> DocumentsResponse:
    page = service.list_active(user.id, limit, offset)
    return DocumentsResponse(
        documents=[document_response(item) for item in page.items],
        pagination=pagination_info(limit, offset, page.total),
    )


@router.get(
    "/documents/trash",
    response_model=TrashResponse,
    summary="Отримати кошик",
    description=(
        "Повертає сторінку демонстраційних документів, переміщених до "
        "кошика."
    ),
    response_description="Документи кошика та метадані пагінації.",
    responses={
        status.HTTP_200_OK: {"description": "Кошик отримано."},
        **COMMON_ERROR_RESPONSES,
    },
)
def list_trash(
    service: Documents,
    user: CurrentUser,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Максимальна кількість документів у відповіді.",
            examples=[20],
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description=(
                "Кількість документів кошика, які потрібно пропустити."
            ),
            examples=[0],
        ),
    ] = 0,
) -> TrashResponse:
    page = service.list_trash(user.id, limit, offset)
    return TrashResponse(
        documents=[document_response(item) for item in page.items],
        pagination=pagination_info(limit, offset, page.total),
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Отримати документ",
    description="Повертає активний документ за його ідентифікатором.",
    response_description="Знайдений документ.",
    responses={
        status.HTTP_200_OK: {"description": "Документ отримано."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def read_document(
    service: Documents,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    user: CurrentUser,
) -> DocumentResponse:
    return document_response(service.get(user.id, document_id))


@router.put(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Перейменувати документ",
    description=(
        "Замінює назву активного документа. Довжина назви — від 1 до "
        "100 символів."
    ),
    response_description="Оновлений документ.",
    responses={
        status.HTTP_200_OK: {"description": "Документ перейменовано."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def update_document(
    service: Documents,
    payload: DocumentUpdate,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    user: CurrentUser,
) -> DocumentResponse:
    document = service.rename(user.id, document_id, payload.title)
    return document_response(document)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Перемістити документ до кошика",
    description=(
        "М'яко видаляє активний документ: він зникає зі списку, "
        "але його можна відновити."
    ),
    response_description=(
        "Документ переміщено до кошика; відповідь не містить тіла."
    ),
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Документ переміщено до кошика."
        },
        **RESOURCE_ERROR_RESPONSES,
    },
)
def move_document_to_trash(
    service: Documents,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    user: CurrentUser,
) -> None:
    service.move_to_trash(user.id, document_id)


@router.post(
    "/documents/{document_id}/restore",
    response_model=DocumentResponse,
    summary="Відновити документ із кошика",
    description=(
        "Повертає документ із кошика до активного списку без зміни "
        "назви та вмісту."
    ),
    response_description="Відновлений документ.",
    responses={
        status.HTTP_200_OK: {"description": "Документ відновлено."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def restore_document(
    service: Documents,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    user: CurrentUser,
) -> DocumentResponse:
    return document_response(service.restore(user.id, document_id))


@router.get(
    "/documents/{document_id}/paragraphs",
    response_model=ParagraphsResponse,
    summary="Отримати абзаци документа",
    description=(
        "Повертає всі абзаци активного документа в порядку їх відображення."
    ),
    response_description="Абзаци документа.",
    responses={
        status.HTTP_200_OK: {"description": "Абзаци отримано."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def list_paragraphs(
    service: Documents,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    user: CurrentUser,
) -> ParagraphsResponse:
    paragraphs = service.list_paragraphs(user.id, document_id)
    return ParagraphsResponse(
        paragraphs=[paragraph_response(item) for item in paragraphs]
    )


@router.post(
    "/documents/{document_id}/paragraphs",
    response_model=ParagraphResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Додати абзац до документа",
    description=(
        "Додає абзац у кінець документа або вставляє його у вказану "
        "нульову позицію."
    ),
    response_description="Створений абзац.",
    responses={
        status.HTTP_201_CREATED: {"description": "Абзац створено."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def create_paragraph(
    service: Documents,
    payload: ParagraphCreate,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    user: CurrentUser,
) -> ParagraphResponse:
    paragraph = service.add_paragraph(
        user.id, document_id, payload.content, payload.position
    )
    return paragraph_response(paragraph)


@router.get(
    "/documents/{document_id}/paragraphs/{paragraph_id}",
    response_model=ParagraphResponse,
    summary="Отримати абзац",
    description="Повертає абзац документа за його ідентифікатором.",
    response_description="Знайдений абзац.",
    responses={
        status.HTTP_200_OK: {"description": "Абзац отримано."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def read_paragraph(
    service: Documents,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    paragraph_id: Annotated[int, PARAGRAPH_PATH_ID],
    user: CurrentUser,
) -> ParagraphResponse:
    paragraph = service.get_paragraph(user.id, document_id, paragraph_id)
    return paragraph_response(paragraph)


@router.patch(
    "/documents/{document_id}/paragraphs/{paragraph_id}",
    response_model=ParagraphResponse,
    summary="Частково оновити абзац",
    description="Змінює лише передані поля абзацу: вміст та/або позицію.",
    response_description="Оновлений абзац.",
    responses={
        status.HTTP_200_OK: {"description": "Абзац оновлено."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def update_paragraph(
    service: Documents,
    payload: ParagraphUpdate,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    paragraph_id: Annotated[int, PARAGRAPH_PATH_ID],
    user: CurrentUser,
) -> ParagraphResponse:
    paragraph = service.update_paragraph(
        user.id, document_id, paragraph_id, payload.content, payload.position
    )
    return paragraph_response(paragraph)


@router.delete(
    "/documents/{document_id}/paragraphs/{paragraph_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалити абзац",
    description=(
        "Видаляє абзац та оновлює позиції абзаців, що йдуть після нього."
    ),
    response_description="Абзац видалено; відповідь не містить тіла.",
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Абзац видалено."},
        **RESOURCE_ERROR_RESPONSES,
    },
)
def delete_paragraph(
    service: Documents,
    document_id: Annotated[int, DOCUMENT_PATH_ID],
    paragraph_id: Annotated[int, PARAGRAPH_PATH_ID],
    user: CurrentUser,
) -> None:
    service.delete_paragraph(user.id, document_id, paragraph_id)


# Moved from main.py by Claude. Reviewed by Kozynska Anastasia
