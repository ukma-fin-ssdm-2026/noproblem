"""Тести надійності планувальника (Лаб 9, знахідка №7).

Тип тесту «обробка помилки»: база даних недоступна (дублер сховища
кидає помилку psycopg), а планувальник не падає, записує збій у журнал
і успішно очищує кошик під час наступного запуску (безпечна відмова).
Дефект у коді, навпаки, не ховається.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import UUID

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from src.documents.bootstrap import build_documents
from src.scheduler.loop import run_periodically
from src.scheduler.service import TrashPurger
from tests.conftest import IamTestEnv
from tests.fakes import FakeClock

SCHEDULER_LOGGER = "notely.scheduler"
OWNER = UUID("00000000-0000-0000-0000-000000000001")


class FlakyDocuments:
    """Дублер сховища: перші ``failures`` викликів кидають ``error``."""

    def __init__(self, error: Exception, failures: int = 1) -> None:
        self._error = error
        self._failures = failures
        self.calls: list[datetime] = []

    def purge_trashed_before(self, cutoff: datetime) -> list[int]:
        self.calls.append(cutoff)
        if len(self.calls) <= self._failures:
            raise self._error
        return [1, 2]


@pytest.mark.req("FR-023")
@pytest.mark.parametrize(
    "error",
    [
        psycopg.OperationalError("connection refused"),
        PoolTimeout("couldn't get a connection after 30.00 sec"),
    ],
    ids=["db-down", "pool-timeout"],
)
def test_db_failure_is_logged_and_retried_next_run(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    documents = FlakyDocuments(error)
    purger = TrashPurger(documents=documents, clock=FakeClock())

    with caplog.at_level(logging.ERROR, logger=SCHEDULER_LOGGER):
        assert purger.run_once() == 0  # не впав

    assert "Не вдалося очистити кошик" in caplog.text
    assert purger.run_once() == 2  # наступний запуск успішний
    assert len(documents.calls) == 2


def test_code_defect_is_not_hidden() -> None:
    """Перехоплюються лише помилки БД; баг у коді має бути видно."""
    purger = TrashPurger(
        documents=FlakyDocuments(TypeError("bug")), clock=FakeClock()
    )

    with pytest.raises(TypeError):
        purger.run_once()


@pytest.mark.req("FR-023")
def test_purges_only_documents_older_than_30_days(env: IamTestEnv) -> None:
    """Справжнє сховище в пам'яті: 30 днів — видалено, 29 — ні."""
    module = build_documents(env.access, clock=env.clock)
    old = module.service.create(OWNER, "old", "Старий").document.id
    module.service.move_to_trash(OWNER, old)
    env.clock.advance(days=1)
    recent = module.service.create(OWNER, "new", "Новий").document.id
    module.service.move_to_trash(OWNER, recent)
    env.clock.advance(days=29)

    purger = TrashPurger(documents=module.documents, clock=env.clock)

    assert purger.run_once() == 1
    assert module.documents.get(old) is None
    assert module.documents.get(recent) is not None


class RecordingPurger:
    """Дублер ``TrashPurger`` для фонового циклу."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self._error = error

    def run_once(self) -> int:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return 0


def test_loop_runs_purger_repeatedly_until_cancelled() -> None:
    purger = RecordingPurger()

    async def scenario() -> None:
        task = asyncio.create_task(run_periodically(purger, 0.01))
        while purger.calls < 2:
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    assert purger.calls >= 2


def test_loop_stops_and_logs_on_code_defect(
    caplog: pytest.LogCaptureFixture,
) -> None:
    purger = RecordingPurger(error=RuntimeError("bug"))

    with caplog.at_level(logging.ERROR, logger=SCHEDULER_LOGGER):
        with pytest.raises(RuntimeError):
            asyncio.run(
                asyncio.wait_for(run_periodically(purger, 0.01), timeout=5)
            )

    assert purger.calls == 1
    assert "Планувальник зупинено" in caplog.text


# File was created by Claude. Reviewed by Kozynska Anastasia
