"""``TrashPurger``: остаточне видалення документів із кошика (FR-023).

Раніше кошик очищувався «ліниво» під час звичайних запитів
(створення документа, перегляд кошика, відновлення). Через це запит
користувача міг чекати на видалення чужих прострочених документів
(знахідка №7 у ``docs/reliability/scavenger-hunt.md``). Тепер
очищення — окрема операція, яку періодично запускає фоновий цикл.

Модуль працює через порт ``DocumentRepository`` і не знає, де лежать
документи: у пам'яті чи в PostgreSQL.
"""

from __future__ import annotations

import logging

import psycopg

from src.documents.ports import DocumentRepository
from src.documents.service import TRASH_RETENTION
from src.iam.ports import Clock

logger = logging.getLogger("notely.scheduler")


class TrashPurger:
    """Видаляє документи, що лежать у кошику довше за 30 днів."""

    def __init__(self, *, documents: DocumentRepository, clock: Clock) -> None:
        self._documents = documents
        self._clock = clock

    def run_once(self) -> int:
        """Один запуск очищення; повертає кількість видалених документів.

        Збій бази даних не зупиняє планувальник: помилка записується в
        журнал, а прострочені документи буде видалено під час
        наступного запуску (безпечна відмова — користувач нічого не
        помічає). Перехоплюються лише помилки БД (``psycopg.Error``,
        зокрема ``PoolTimeout``); будь-яка інша помилка — це дефект у
        коді, і її не можна ховати.
        """
        cutoff = self._clock.now() - TRASH_RETENTION
        try:
            purged = self._documents.purge_trashed_before(cutoff)
        except psycopg.Error:
            logger.exception(
                "Не вдалося очистити кошик; повторна спроба під час "
                "наступного запуску планувальника."
            )
            return 0
        if purged:
            logger.info(
                "Остаточно видалено документів із кошика: %d", len(purged)
            )
        return len(purged)


# File was created by Claude. Reviewed by Kozynska Anastasia
