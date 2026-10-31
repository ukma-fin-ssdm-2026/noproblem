"""Потокобезпечність сховища документів у пам'яті процесу."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import UUID

import pytest

from src.documents.adapters import (
    InMemoryDocumentRepository,
    InMemoryDocumentStore,
)
from src.documents.models import CreateOutcome

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
OWNER_ID = UUID("00000000-0000-0000-0000-00000000000a")
WORKERS = 24


def create_simultaneously(
    repository: InMemoryDocumentRepository, keys: list[str]
) -> list[CreateOutcome]:
    barrier = Barrier(len(keys))

    def create(key: str) -> CreateOutcome:
        barrier.wait(timeout=10)
        return repository.create(OWNER_ID, key, "Паралельний документ", NOW)

    with ThreadPoolExecutor(max_workers=len(keys)) as executor:
        return list(executor.map(create, keys))


@pytest.mark.req("FR-013")
def test_concurrent_creates_with_same_key_return_one_document() -> None:
    repository = InMemoryDocumentRepository(InMemoryDocumentStore())

    outcomes = create_simultaneously(repository, ["same-key"] * WORKERS)

    assert len({outcome.document.id for outcome in outcomes}) == 1
    assert sum(outcome.created for outcome in outcomes) == 1


@pytest.mark.req("FR-013")
def test_concurrent_creates_with_different_keys_get_unique_ids() -> None:
    repository = InMemoryDocumentRepository(InMemoryDocumentStore())

    outcomes = create_simultaneously(
        repository, [f"key-{index}" for index in range(WORKERS)]
    )

    ids = [outcome.document.id for outcome in outcomes]
    assert len(ids) == len(set(ids)) == WORKERS
    assert all(outcome.created for outcome in outcomes)


# p.s. File was created with Copilot assistance and reviewed by Olha Bidochka
