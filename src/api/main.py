from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
import logging
import os
import pathlib
from typing import Annotated, AsyncGenerator

import yaml

from fastapi import APIRouter, FastAPI, Header, HTTPException, Path, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.auth.errors import register_iam_error_handlers
from src.api.auth.routes import router as auth_router
from src.api.common import (
    AUTH_ERROR_RESPONSES,
    VALIDATION_ERROR_RESPONSE,
    ApiError,
)
from src.iam import AuthService, IamSettings, build_iam


logger = logging.getLogger(__name__)


class AccessMode(str, Enum):
    restricted = "restricted"
    link = "link"


class DocumentCreate(BaseModel):
    """Поля для створення документа."""

    model_config = ConfigDict(str_strip_whitespace=True)
    title: str | None = Field(
        default=None,
        max_length=100,
        description="Назва документа. Якщо її не вказано, використовується «Без назви».",
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

    id: int = Field(description="Унікальний ідентифікатор документа.", examples=[1])
    title: str = Field(description="Назва документа.", examples=["Нотатки команди"])
    access_mode: AccessMode = Field(description="Режим доступу до документа.")
    created_at: datetime = Field(description="Час створення документа в UTC.")
    updated_at: datetime = Field(description="Час останньої зміни документа в UTC.")
    deleted_at: datetime | None = Field(
        default=None,
        description="Час переміщення документа до кошика; null для активного документа.",
    )


class ParagraphCreate(BaseModel):
    """Поля для додавання абзацу в кінець документа або у вказану позицію."""

    content: str = Field(
        description="Текст абзацу. Порожній текст дозволений для порожнього абзацу.",
        examples=["Текст першого абзацу"],
    )
    position: int | None = Field(
        default=None,
        ge=0,
        description="Нульова позиція вставлення; якщо не вказано, абзац додається в кінець.",
        examples=[0],
    )


class ParagraphUpdate(BaseModel):
    """Поля для зміни вмісту та/або позиції абзацу."""

    content: str | None = Field(
        default=None,
        description="Новий текст абзацу; null або пропуск залишає текст без змін.",
        examples=["Оновлений текст абзацу"],
    )
    position: int | None = Field(
        default=None,
        ge=0,
        description="Нова нульова позиція абзацу; позиції поза документом відхиляються.",
        examples=[1],
    )

    @model_validator(mode="after")
    def require_an_update(self) -> "ParagraphUpdate":
        if self.content is None and self.position is None:
            raise ValueError("Потрібно вказати новий вміст або нову позицію абзацу.")
        return self


class ParagraphResponse(BaseModel):
    """Абзац документа."""

    id: int = Field(description="Унікальний ідентифікатор абзацу.", examples=[1])
    document_id: int = Field(description="Ідентифікатор документа-власника.", examples=[1])
    position: int = Field(ge=0, description="Позиція абзацу, починаючи з нуля.", examples=[0])
    content: str = Field(description="Текст абзацу.", examples=["Текст документа"])


class PaginationInfo(BaseModel):
    """Метадані пагінації списку."""

    limit: int = Field(ge=1, le=100, description="Максимальна кількість елементів у відповіді.")
    offset: int = Field(ge=0, description="Кількість пропущених елементів.")
    total: int = Field(ge=0, description="Загальна кількість елементів.")
    has_more: bool = Field(description="Чи є елементи на наступній сторінці.")


class DocumentsResponse(BaseModel):
    """Сторінка активних документів."""

    documents: list[DocumentResponse] = Field(description="Документи на поточній сторінці.")
    pagination: PaginationInfo = Field(description="Метадані пагінації.")


class TrashResponse(BaseModel):
    """Сторінка документів у кошику."""

    documents: list[DocumentResponse] = Field(
        description="Документи в кошику на поточній сторінці."
    )
    pagination: PaginationInfo = Field(description="Метадані пагінації.")


class ParagraphsResponse(BaseModel):
    """Список абзаців документа у порядку відображення."""

    paragraphs: list[ParagraphResponse] = Field(description="Абзаци документа.")


COMMON_ERROR_RESPONSES = {
    **AUTH_ERROR_RESPONSES,
    status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR_RESPONSE,
}

RESOURCE_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ApiError,
        "description": (
            "Документ або абзац не знайдено, або ресурс не перебуває " "в очікуваному стані."
        ),
        "content": {"application/json": {"example": {"detail": "Документ не знайдено."}}},
    },
}

DOCUMENT_PATH_ID = Path(
    gt=0,
    description="Додатний ідентифікатор документа.",
    examples=[1],
)
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


OPENAPI_PATH = pathlib.Path(os.getenv("OPENAPI_PATH", "docs/api/openapi-generated.yaml"))


def export_openapi(app: FastAPI) -> bool:
    try:
        OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
        OPENAPI_PATH.write_text(
            yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except OSError:
        logger.warning(
            "Could not write OpenAPI specification to %s",
            OPENAPI_PATH,
            exc_info=True,
        )
        return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    export_openapi(app)
    yield


def create_app(iam: AuthService | None = None) -> FastAPI:
    """Створює застосунок.

    Args:
        iam: Готовий сервіс IAM. Тести передають сюди сервіс із
            підробленим годинником; за замовчуванням він збирається з
            налаштувань оточення.
    """
    app = FastAPI(
        title="NoteLy API",
        version="1.0.0",
        docs_url="/api-docs",
        lifespan=lifespan,
        description=(
            "Демонстраційний API NoteLy: автентифікація (модуль IAM), "
            "документи, кошик і абзаци. Дані зберігаються лише в пам'яті "
            "та скидаються після перезапуску. Маршрути /auth працюють "
            "повністю; для маршрутів документів відповіді 401/403 поки "
            "документують інтеграційний контракт з IAM, перевірка ролей "
            "буде підключена в наступній частині."
        ),
    )

    app.state.iam = iam or build_iam(IamSettings.from_env())
    register_iam_error_handlers(app)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        error = ApiError(detail="Некоректні вхідні дані.")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error.model_dump(),
        )

    router = APIRouter(prefix="/api/v1", tags=["documents"])

    demo_document = DocumentResponse(
        id=1,
        title="Нотатки команди",
        access_mode=AccessMode.restricted,
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    documents: dict[int, DocumentResponse] = {demo_document.id: demo_document}
    paragraphs: dict[int, list[ParagraphResponse]] = {demo_document.id: []}
    idempotency_records: dict[str, tuple[str, DocumentResponse]] = {}
    next_document_id = 2
    next_paragraph_id = 1

    def get_active_document_or_404(document_id: int) -> DocumentResponse:
        document = documents.get(document_id)
        if document is None or document.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Активний документ з id={document_id} не знайдено.",
            )
        return document

    def get_trashed_document_or_404(document_id: int) -> DocumentResponse:
        document = documents.get(document_id)
        if document is None or document.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Документ з id={document_id} не знайдено в кошику.",
            )
        return document

    def find_paragraph_or_404(document_id: int, paragraph_id: int) -> ParagraphResponse:
        for paragraph in paragraphs[document_id]:
            if paragraph.id == paragraph_id:
                return paragraph
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Абзац з id={paragraph_id} не знайдено в документі {document_id}.",
        )

    @router.post(
        "/documents",
        response_model=DocumentResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Створити документ",
        description=(
            "Створює документ з обмеженим доступом. Заголовок Idempotency-Key обов'язковий. "
            "Повтор із тим самим ключем і тією самою назвою повертає той самий документ "
            "зі статусом 201; повторне використання ключа з іншою назвою повертає 409."
        ),
        response_description="Створений документ або результат повтору ідемпотентного запиту.",
        responses={
            status.HTTP_201_CREATED: {
                "description": "Документ створено або повернено результат попереднього запиту."
            },
            status.HTTP_409_CONFLICT: {
                "model": ApiError,
                "description": "Ключ ідемпотентності вже використаний з іншим вмістом запиту.",
                "content": {
                    "application/json": {
                        "example": {
                            "detail": "Idempotency-Key вже використаний з іншою назвою документа."
                        }
                    }
                },
            },
            **COMMON_ERROR_RESPONSES,
        },
    )
    def create_document(
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=128,
                description="Унікальний ключ для безпечного повтору запиту створення.",
                examples=["create-document-request-001"],
            ),
        ],
        payload: DocumentCreate | None = None,
    ) -> DocumentResponse:
        nonlocal next_document_id
        effective_title = (payload.title if payload else None) or "Без назви"
        previous_request = idempotency_records.get(idempotency_key)
        if previous_request is not None:
            previous_title, previous_document = previous_request
            if previous_title != effective_title:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key вже використаний з іншою назвою документа.",
                )
            return previous_document

        now = datetime.now(timezone.utc)
        document = DocumentResponse(
            id=next_document_id,
            title=effective_title,
            access_mode=AccessMode.restricted,
            created_at=now,
            updated_at=now,
        )
        next_document_id += 1
        documents[document.id] = document
        paragraphs[document.id] = []
        idempotency_records[idempotency_key] = (effective_title, document)
        return document

    @router.get(
        "/documents",
        response_model=DocumentsResponse,
        summary="Отримати список активних документів",
        description="Повертає сторінку активних документів; документи з кошика не включаються.",
        response_description="Документи та метадані пагінації.",
        responses={
            status.HTTP_200_OK: {"description": "Список документів отримано."},
            **COMMON_ERROR_RESPONSES,
        },
    )
    def list_documents(
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
                description="Кількість активних документів, які потрібно пропустити.",
                examples=[0],
            ),
        ] = 0,
    ) -> DocumentsResponse:
        active_documents = sorted(
            (document for document in documents.values() if document.deleted_at is None),
            key=lambda document: document.id,
        )
        page = active_documents[offset : offset + limit]
        return DocumentsResponse(
            documents=page,
            pagination=pagination_info(limit, offset, len(active_documents)),
        )

    @router.get(
        "/documents/trash",
        response_model=TrashResponse,
        summary="Отримати кошик",
        description="Повертає сторінку демонстраційних документів, переміщених до кошика.",
        response_description="Документи кошика та метадані пагінації.",
        responses={
            status.HTTP_200_OK: {"description": "Кошик отримано."},
            **COMMON_ERROR_RESPONSES,
        },
    )
    def list_trash(
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
                description="Кількість документів кошика, які потрібно пропустити.",
                examples=[0],
            ),
        ] = 0,
    ) -> TrashResponse:
        trashed_documents = sorted(
            (document for document in documents.values() if document.deleted_at is not None),
            key=lambda document: document.deleted_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        page = trashed_documents[offset : offset + limit]
        return TrashResponse(
            documents=page,
            pagination=pagination_info(limit, offset, len(trashed_documents)),
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
        document_id: Annotated[int, DOCUMENT_PATH_ID],
    ) -> DocumentResponse:
        return get_active_document_or_404(document_id)

    @router.put(
        "/documents/{document_id}",
        response_model=DocumentResponse,
        summary="Перейменувати документ",
        description="Замінює назву активного документа. Довжина назви — від 1 до 100 символів.",
        response_description="Оновлений документ.",
        responses={
            status.HTTP_200_OK: {"description": "Документ перейменовано."},
            **RESOURCE_ERROR_RESPONSES,
        },
    )
    def update_document(
        payload: DocumentUpdate,
        document_id: Annotated[int, DOCUMENT_PATH_ID],
    ) -> DocumentResponse:
        document = get_active_document_or_404(document_id)
        updated_document = document.model_copy(
            update={"title": payload.title, "updated_at": datetime.now(timezone.utc)}
        )
        documents[document_id] = updated_document
        return updated_document

    @router.delete(
        "/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Перемістити документ до кошика",
        description=(
            "М'яко видаляє активний документ: він зникає зі списку, " "але його можна відновити."
        ),
        response_description="Документ переміщено до кошика; відповідь не містить тіла.",
        responses={
            status.HTTP_204_NO_CONTENT: {"description": "Документ переміщено до кошика."},
            **RESOURCE_ERROR_RESPONSES,
        },
    )
    def move_document_to_trash(
        document_id: Annotated[int, DOCUMENT_PATH_ID],
    ) -> None:
        document = get_active_document_or_404(document_id)
        now = datetime.now(timezone.utc)
        documents[document_id] = document.model_copy(update={"deleted_at": now, "updated_at": now})

    @router.post(
        "/documents/{document_id}/restore",
        response_model=DocumentResponse,
        summary="Відновити документ із кошика",
        description="Повертає документ із кошика до активного списку без зміни назви та вмісту.",
        response_description="Відновлений документ.",
        responses={
            status.HTTP_200_OK: {"description": "Документ відновлено."},
            **RESOURCE_ERROR_RESPONSES,
        },
    )
    def restore_document(
        document_id: Annotated[int, DOCUMENT_PATH_ID],
    ) -> DocumentResponse:
        document = get_trashed_document_or_404(document_id)
        restored_document = document.model_copy(
            update={"deleted_at": None, "updated_at": datetime.now(timezone.utc)}
        )
        documents[document_id] = restored_document
        return restored_document

    @router.get(
        "/documents/{document_id}/paragraphs",
        response_model=ParagraphsResponse,
        summary="Отримати абзаци документа",
        description="Повертає всі абзаци активного документа в порядку їх відображення.",
        response_description="Абзаци документа.",
        responses={
            status.HTTP_200_OK: {"description": "Абзаци отримано."},
            **RESOURCE_ERROR_RESPONSES,
        },
    )
    def list_paragraphs(
        document_id: Annotated[int, DOCUMENT_PATH_ID],
    ) -> ParagraphsResponse:
        get_active_document_or_404(document_id)
        ordered_paragraphs = sorted(
            paragraphs[document_id], key=lambda paragraph: paragraph.position
        )
        return ParagraphsResponse(paragraphs=ordered_paragraphs)

    @router.post(
        "/documents/{document_id}/paragraphs",
        response_model=ParagraphResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Додати абзац до документа",
        description="Додає абзац у кінець документа або вставляє його у вказану нульову позицію.",
        response_description="Створений абзац.",
        responses={
            status.HTTP_201_CREATED: {"description": "Абзац створено."},
            **RESOURCE_ERROR_RESPONSES,
        },
    )
    def create_paragraph(
        payload: ParagraphCreate,
        document_id: Annotated[int, DOCUMENT_PATH_ID],
    ) -> ParagraphResponse:
        nonlocal next_paragraph_id
        get_active_document_or_404(document_id)
        ordered_paragraphs = sorted(
            paragraphs[document_id], key=lambda paragraph: paragraph.position
        )
        position = len(ordered_paragraphs) if payload.position is None else payload.position
        if position > len(ordered_paragraphs):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Позиція вставлення не може бути більшою за кількість абзаців.",
            )
        ordered_paragraphs.insert(
            position,
            ParagraphResponse(
                id=next_paragraph_id,
                document_id=document_id,
                position=position,
                content=payload.content,
            ),
        )
        next_paragraph_id += 1
        paragraphs[document_id] = [
            paragraph.model_copy(update={"position": index})
            for index, paragraph in enumerate(ordered_paragraphs)
        ]
        document = documents[document_id]
        documents[document_id] = document.model_copy(
            update={"updated_at": datetime.now(timezone.utc)}
        )
        return paragraphs[document_id][position]

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
        document_id: Annotated[int, DOCUMENT_PATH_ID],
        paragraph_id: Annotated[int, PARAGRAPH_PATH_ID],
    ) -> ParagraphResponse:
        get_active_document_or_404(document_id)
        return find_paragraph_or_404(document_id, paragraph_id)

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
        payload: ParagraphUpdate,
        document_id: Annotated[int, DOCUMENT_PATH_ID],
        paragraph_id: Annotated[int, PARAGRAPH_PATH_ID],
    ) -> ParagraphResponse:
        get_active_document_or_404(document_id)
        target = find_paragraph_or_404(document_id, paragraph_id)
        ordered_paragraphs = sorted(
            paragraphs[document_id], key=lambda paragraph: paragraph.position
        )
        old_position = target.position
        new_position = old_position if payload.position is None else payload.position
        if new_position >= len(ordered_paragraphs):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Нова позиція має бути в межах наявних позицій абзаців.",
            )
        ordered_paragraphs.pop(old_position)
        updated_target = target.model_copy(
            update={
                "content": target.content if payload.content is None else payload.content,
                "position": new_position,
            }
        )
        ordered_paragraphs.insert(new_position, updated_target)
        paragraphs[document_id] = [
            paragraph.model_copy(update={"position": index})
            for index, paragraph in enumerate(ordered_paragraphs)
        ]
        document = documents[document_id]
        documents[document_id] = document.model_copy(
            update={"updated_at": datetime.now(timezone.utc)}
        )
        return find_paragraph_or_404(document_id, paragraph_id)

    @router.delete(
        "/documents/{document_id}/paragraphs/{paragraph_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Видалити абзац",
        description="Видаляє абзац та оновлює позиції абзаців, що йдуть після нього.",
        response_description="Абзац видалено; відповідь не містить тіла.",
        responses={
            status.HTTP_204_NO_CONTENT: {"description": "Абзац видалено."},
            **RESOURCE_ERROR_RESPONSES,
        },
    )
    def delete_paragraph(
        document_id: Annotated[int, DOCUMENT_PATH_ID],
        paragraph_id: Annotated[int, PARAGRAPH_PATH_ID],
    ) -> None:
        get_active_document_or_404(document_id)
        target = find_paragraph_or_404(document_id, paragraph_id)
        remaining = [
            paragraph for paragraph in paragraphs[document_id] if paragraph.id != target.id
        ]
        paragraphs[document_id] = [
            paragraph.model_copy(update={"position": index})
            for index, paragraph in enumerate(sorted(remaining, key=lambda item: item.position))
        ]
        document = documents[document_id]
        documents[document_id] = document.model_copy(
            update={"updated_at": datetime.now(timezone.utc)}
        )

    app.include_router(router)
    app.include_router(auth_router, prefix="/api/v1")
    return app


app = create_app()

"This file was modified by Copilot and Claude. Reviewed by Kozynska Anastasia"
