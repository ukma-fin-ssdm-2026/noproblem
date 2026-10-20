"""Спільні фікстури для HTTP-тестів API.

Фікстура ``client`` раніше була продубльована в кожному файлі
``tests/api`` (і копії трохи відрізнялися). Тепер вона одна: застосунок
збирається з тими самими підробками IAM, що й у ``tests/conftest.py``
(годинник, хешер, пошта), тож тести API не залежать від реального
часу, Argon2 чи SMTP.
"""

from __future__ import annotations

from datetime import datetime, tzinfo

import pytest
from fastapi.testclient import TestClient

import src.api.main as main_module
from src.api.main import create_app
from tests.conftest import IamTestEnv
from tests.fakes import FakeClock


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    """HTTP-клієнт до свіжого застосунку з ізольованим станом."""
    return TestClient(create_app(iam=env.iam, access=env.access))


@pytest.fixture
def api_clock(env: IamTestEnv, monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Підміняє реальний час у маршрутах документів (``src/api/main.py``).

    Маршрути беруть час напряму з ``datetime.now``, а не через порт
    ``Clock``, тож без підміни ``created_at``/``updated_at`` залежать від
    годинника комп'ютера і їх не можна точно перевірити. Заглушка
    підставляє підклас ``datetime``, у якого ``now()`` повертає час
    ``env.clock``. Так у всього застосунку (і IAM, і документів) одне
    джерело часу, яке тест «перемотує» через ``api_clock.advance(...)``.

    Увага: сесія закінчується після 30 хв бездіяльності, тож перемотуйте
    час кроками, коротшими за 30 хв.
    """
    clock = env.clock

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            current = clock.now()
            return current if tz is None else current.astimezone(tz)

    monkeypatch.setattr(main_module, "datetime", FrozenDatetime)
    return clock


# File was created by Claude. Reviewed by Kozynska Anastasia
