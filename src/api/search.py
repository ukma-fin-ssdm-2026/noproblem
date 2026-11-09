"""HTTP-маршрути пошуку документів."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request, status
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from src.api.common import ApiError, error_response
from src.api.security import require_user
from src.iam import UserView
from src.search.errors import SearchUnavailableError
from src.search.service import SearchService

router = APIRouter(prefix="/search", tags=["search"])

MAX_SEARCH_QUERY_LENGTH = 10_000
SEARCH_UNAVAILABLE_DETAIL = "Пошук тимчасово недоступний. Спробуйте пізніше."


class SearchResultResponse(BaseModel):
    """Результат пошуку документа."""

    doc_id: int
    title: str
    snippet: str


def get_search_service(request: Request) -> SearchService:
    """Повертає сервіс пошуку, створений під час конфігурації застосунку."""
    return request.app.state.search_service


CurrentUser = Annotated[UserView, Depends(require_user)]
Search = Annotated[SearchService, Depends(get_search_service)]


def register_search_error_handlers(app: FastAPI) -> None:
    async def handle_search_unavailable(
        _request: Request, _exc: SearchUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ApiError(detail=SEARCH_UNAVAILABLE_DETAIL).model_dump(),
        )

    app.add_exception_handler(
        SearchUnavailableError, handle_search_unavailable
    )


@router.get(
    "",
    response_model=list[SearchResultResponse],
    summary="Знайти документи",
    description=(
        "Шукає збіги в назвах і вмісті абзаців серед активних "
        "документів, до яких користувач має доступ."
    ),
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            "Пошук тимчасово недоступний.",
            SEARCH_UNAVAILABLE_DETAIL,
        )
    },
)
def search_documents(
    q: Annotated[
        str,
        Query(
            min_length=2,
            max_length=MAX_SEARCH_QUERY_LENGTH,
            description="Пошуковий текст (від 2 до 10 000 символів).",
            examples=["quarterly"],
        ),
    ],
    user: CurrentUser,
    service: Search,
) -> list[SearchResultResponse]:
    return [
        SearchResultResponse(
            doc_id=result.doc_id,
            title=result.title,
            snippet=result.snippet,
        )
        for result in service.search(user_id=user.id, query=q)
    ]
