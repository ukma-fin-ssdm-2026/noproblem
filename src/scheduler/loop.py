"""Фоновий цикл планувальника та його налаштування з оточення.

Цикл запускається в ``lifespan`` застосунку (``src/api/main.py``) і
раз на ``interval_s`` секунд викликає ``TrashPurger.run_once()``.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os

from src.scheduler.service import TrashPurger

logger = logging.getLogger("notely.scheduler")

TRASH_PURGE_INTERVAL_ENV = "TRASH_PURGE_INTERVAL_S"
DEFAULT_TRASH_PURGE_INTERVAL_S = 3600.0  # раз на годину


def trash_purge_interval_from_env() -> float | None:
    """Інтервал очищення кошика в секундах або ``None``, якщо вимкнено.

    ``TRASH_PURGE_INTERVAL_S`` не задано → раз на годину; ``0`` →
    планувальник вимкнено.

    Raises:
        ValueError: Значення не є скінченним числом (зокрема ``nan``,
            ``inf``) або від'ємне. Застосунок не
            стартує з хибним налаштуванням (швидка відмова), а не
            мовчки працює без очищення кошика.
    """
    raw = os.environ.get(TRASH_PURGE_INTERVAL_ENV, "").strip()
    if not raw:
        return DEFAULT_TRASH_PURGE_INTERVAL_S
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(
            f"{TRASH_PURGE_INTERVAL_ENV} має бути числом секунд, "
            f"отримано {raw!r}."
        ) from None
    if not math.isfinite(value):
        # float() приймає "nan" та "inf": nan проходить перевірку < 0,
        # а inf означав би, що планувальник ніколи не спрацює.
        raise ValueError(
            f"{TRASH_PURGE_INTERVAL_ENV} має бути скінченним числом, "
            f"отримано {raw!r}."
        )
    if value < 0:
        raise ValueError(f"{TRASH_PURGE_INTERVAL_ENV} не може бути від'ємним.")
    return value or None


async def run_periodically(purger: TrashPurger, interval_s: float) -> None:
    """Безкінечний цикл: зачекати ``interval_s``, очистити кошик, знову.

    Спершу чекаємо, а потім очищуємо: так запуск застосунку (і тести,
    що його запускають) не залежить від роботи з кошиком. Документи,
    старші за 30 днів, і так не видно користувачам, тож затримка до
    першого запуску нічого не змінює для них.

    ``run_once`` синхронний (репозиторії синхронні), тому він
    виконується в окремому потоці через ``asyncio.to_thread``: інакше
    він блокував би event loop, як у знахідці №4.
    """
    while True:
        await asyncio.sleep(interval_s)
        try:
            await asyncio.to_thread(purger.run_once)
        except Exception:
            # Помилки БД run_once обробляє сам; сюди доходить лише
            # дефект у коді. Його не ховаємо: пишемо в журнал і
            # зупиняємо цикл (швидка відмова), щоб помилку помітили.
            logger.exception(
                "Планувальник зупинено через непередбачену помилку."
            )
            raise


# File was created by Claude. Reviewed by Kozynska Anastasia
