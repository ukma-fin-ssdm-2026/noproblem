"""Тести потокобезпечного менеджера блокувань абзаців."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

from src.collab.locks import LockManager


def test_acquire_is_idempotent_for_holder_and_exclusive_for_others() -> None:
    manager = LockManager()
    owner = uuid4()
    other = uuid4()

    assert manager.acquire(1, 2, owner)
    assert manager.acquire(1, 2, owner)
    assert not manager.acquire(1, 2, other)
    assert manager.holder(1, 2) == owner


def test_release_only_removes_lock_owned_by_user() -> None:
    manager = LockManager()
    owner = uuid4()
    other = uuid4()
    manager.acquire(1, 2, owner)

    assert not manager.release(1, 2, other)
    assert manager.holder(1, 2) == owner
    assert manager.release(1, 2, owner)
    assert manager.holder(1, 2) is None


def test_release_all_is_limited_to_user_and_document() -> None:
    manager = LockManager()
    owner = uuid4()
    other = uuid4()
    manager.acquire(1, 2, owner)
    manager.acquire(1, 3, owner)
    manager.acquire(2, 2, owner)
    manager.acquire(1, 4, other)

    assert set(manager.release_all(1, owner)) == {2, 3}
    assert manager.locks(1) == {4: other}
    assert manager.locks(2) == {2: owner}


def test_same_paragraph_id_in_different_documents_is_independent() -> None:
    manager = LockManager()
    first = uuid4()
    second = uuid4()

    assert manager.acquire(1, 1, first)
    assert manager.acquire(2, 1, second)
    assert manager.locks(1) == {1: first}
    assert manager.locks(2) == {1: second}


def test_concurrent_acquire_has_exactly_one_winner() -> None:
    manager = LockManager()
    users: list[UUID] = [uuid4() for _ in range(10)]
    barrier = Barrier(len(users))

    def acquire(user_id: UUID) -> bool:
        barrier.wait()
        return manager.acquire(7, 9, user_id)

    with ThreadPoolExecutor(max_workers=len(users)) as executor:
        results = list(executor.map(acquire, users))

    assert sum(results) == 1
    assert manager.holder(7, 9) in users
