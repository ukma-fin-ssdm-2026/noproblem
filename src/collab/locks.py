"""Потокобезпечні блокування абзаців у пам'яті процесу."""

from __future__ import annotations

from threading import Lock
from uuid import UUID


class LockManager:
    """Зберігає власника кожного заблокованого абзацу."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._holders: dict[tuple[int, int], UUID] = {}

    def acquire(
        self, document_id: int, paragraph_id: int, user_id: UUID
    ) -> bool:
        """Заблокувати вільний абзац або повторно взяти власне блокування."""
        key = (document_id, paragraph_id)
        with self._lock:
            holder = self._holders.get(key)
            if holder is not None and holder != user_id:
                return False
            self._holders[key] = user_id
            return True

    def release(
        self, document_id: int, paragraph_id: int, user_id: UUID
    ) -> bool:
        """Зняти блокування лише тоді, коли воно належить користувачу."""
        key = (document_id, paragraph_id)
        with self._lock:
            if self._holders.get(key) != user_id:
                return False
            del self._holders[key]
            return True

    def release_all(self, document_id: int, user_id: UUID) -> list[int]:
        """Зняти всі блокування користувача в одному документі."""
        with self._lock:
            released = [
                paragraph_id
                for (
                    locked_document_id,
                    paragraph_id,
                ), holder in self._holders.items()
                if locked_document_id == document_id and holder == user_id
            ]
            for paragraph_id in released:
                del self._holders[(document_id, paragraph_id)]
            return released

    def holder(self, document_id: int, paragraph_id: int) -> UUID | None:
        """Повернути власника блокування або ``None``, якщо абзац вільний."""
        with self._lock:
            return self._holders.get((document_id, paragraph_id))

    def locks(self, document_id: int) -> dict[int, UUID]:
        """Повернути копію всіх блокувань документа."""
        with self._lock:
            return {
                paragraph_id: holder
                for (
                    locked_document_id,
                    paragraph_id,
                ), holder in self._holders.items()
                if locked_document_id == document_id
            }
