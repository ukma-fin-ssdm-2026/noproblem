"""Складання застосунку NoteLy: FastAPI, модулі й маршрути.

Тут лише ``create_app()``: створення сервісів (IAM, документи, пошук),
обробники помилок і підключення роутерів.
"""

from contextlib import asynccontextmanager
import logging
import os
import pathlib
from typing import AsyncGenerator

import yaml

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.access import router as access_router
from src.api.auth.errors import register_iam_error_handlers
from src.api.auth.routes import router as auth_router
from src.api.calendar import (
    register_calendar_error_handlers,
    router as calendar_router,
)
from src.api.common import ApiError
from src.api.documents import register_document_error_handlers
from src.api.documents import router as documents_router
from src.api.metrics import install_metrics
from src.api.search import router as search_router
from src.calendar_events.bootstrap import build_calendar
from src.db import create_pool, database_url, load_env_file
from src.documents.bootstrap import build_documents
from src.iam import (
    AccessService,
    AuthService,
    IamSettings,
    build_access,
    build_iam,
)
from src.iam.adapters import SystemClock
from src.iam.ports import Clock
from src.search.service import SearchService

logger = logging.getLogger(__name__)


OPENAPI_PATH = pathlib.Path(
    os.getenv("OPENAPI_PATH", "docs/api/openapi-generated.yaml")
)


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
    pool = getattr(app.state, "database_pool", None)
    try:
        if pool is not None:
            pool.open(wait=True, timeout=10)
        yield
    finally:
        if pool is not None:
            pool.close()


def create_app(
    iam: AuthService | None = None,
    access: AccessService | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Створює застосунок.

    Args:
        iam: Готовий сервіс автентифікації. Тести передають сюди сервіс
            із підробленим годинником; за замовчуванням він збирається з
            налаштувань оточення.
        access: Готовий сервіс доступу до документів; за замовчуванням
            створюється на основі ``iam``.
        clock: Годинник для документів (``created_at``, ``updated_at``,
            кошик). Тести передають той самий підроблений годинник, що й
            IAM; за замовчуванням — системний (UTC).
    """
    app = FastAPI(
        title="NoteLy API",
        version="1.0.0",
        docs_url="/api-docs",
        lifespan=lifespan,
        description=(
            "Прототип API NoteLy: автентифікація, документи, кошик, абзаци "
            "та спільний доступ з ролями Owner / Editor / Guest (модуль "
            "IAM). Маршрути документів вимагають токен сесії. Сховища IAM "
            "працюють у пам'яті або PostgreSQL залежно від DATABASE_URL."
        ),
    )

    app_clock = clock or SystemClock()
    load_env_file()
    url = database_url()
    database_pool = (
        create_pool(url, open_immediately=False)
        if url and iam is None and access is None
        else None
    )
    app.state.database_pool = database_pool
    app.state.iam = iam or build_iam(
        IamSettings.from_env(), clock=app_clock, pool=database_pool
    )
    app.state.access = access or build_access(
        app.state.iam, clock=app_clock, pool=database_pool
    )
    access_service: AccessService = app.state.access
    app.state.documents = build_documents(access_service, clock=app_clock)
    access_service.bind_documents(app.state.documents.documents)
    app.state.search_service = SearchService(
        document_repo=app.state.documents.documents,
        paragraph_repo=app.state.documents.paragraphs,
        access_service=access_service,
    )
    app.state.calendar = build_calendar(
        access_service, app.state.iam, pool=database_pool
    )
    register_iam_error_handlers(app)
    register_document_error_handlers(app)
    register_calendar_error_handlers(app)

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

    install_metrics(app)
    app.include_router(documents_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(access_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(calendar_router, prefix="/api/v1")
    return app


app = create_app()

# This file was modified by Copilot and Claude.
# Reviewed by Kozynska Anastasia and Olha Marushchenko.
