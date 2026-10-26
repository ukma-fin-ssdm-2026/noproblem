"""HTTP-маршрути пошуку документів."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from src.api.security import require_user
from src.iam import UserView
from src.search.service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


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


@router.get(
    "",
    response_model=list[SearchResultResponse],
    summary="Знайти документи",
    description=(
        "Шукає збіги в назвах і вмісті абзаців серед активних "
        "документів, до яких користувач має доступ."
    ),
)
def search_documents(
    q: Annotated[
        str,
        Query(
            min_length=2,
            description="Пошуковий текст (щонайменше 2 символи).",
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
