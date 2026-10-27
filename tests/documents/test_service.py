"""Юніт-тести ``DocumentService``, яких немає серед тестів API.

Решта правил документів (ідемпотентність, права, кошик, абзаци)
перевіряється через HTTP у ``tests/api`` — ці тести проходять через
той самий сервіс. Тут лише те, що через API не видно: сервіс очищує
кошик рівно через 30 днів. Що саме видаляється разом із документом,
перевіряють тести сховищ (``test_repositories.py``).
"""

from __future__ import annotations

from uuid import UUID

import pytest

from src.documents.bootstrap import build_documents
from src.documents.errors import DocumentNotInTrashError
from tests.conftest import IamTestEnv

OWNER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.parametrize(
    ("elapsed", "still_in_trash"),
    [({"days": 29, "hours": 23}, True), ({"days": 30}, False)],
    ids=["29d23h-kept", "30d-purged"],
)
def test_trash_is_purged_exactly_after_30_days(
    env: IamTestEnv, elapsed: dict[str, float], still_in_trash: bool
) -> None:
    """FR-023: документ можна відновити лише до спливу 30 днів."""
    service = build_documents(env.access, clock=env.clock).service
    document_id = service.create(OWNER, "key", "Звіт").document.id
    service.move_to_trash(OWNER, document_id)
    env.clock.advance(**elapsed)

    if still_in_trash:
        assert service.restore(OWNER, document_id).deleted_at is None
    else:
        with pytest.raises(DocumentNotInTrashError):
            service.restore(OWNER, document_id)


# File was created by Claude. Reviewed by Kozynska Anastasia
