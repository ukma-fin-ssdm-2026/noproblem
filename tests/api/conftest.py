"""Спільні фікстури для HTTP-тестів API.

Фікстура ``client`` раніше була продубльована в кожному файлі
``tests/api`` (і копії трохи відрізнялися). Тепер вона одна: застосунок
збирається з тими самими підробками IAM, що й у ``tests/conftest.py``
(годинник, хешер, пошта), тож тести API не залежать від реального
часу, Argon2 чи SMTP.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from tests.conftest import IamTestEnv
from tests.fakes import FakeClock


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    """HTTP-клієнт до свіжого застосунку з ізольованим станом."""
    return TestClient(
        create_app(iam=env.iam, access=env.access, clock=env.clock)
    )


@pytest.fixture
def api_clock(env: IamTestEnv) -> FakeClock:
    """Годинник застосунку, яким тест керує через ``advance(...)``.

    Застосунок отримує годинник через ``create_app(clock=...)``, тож
    IAM і документи мають одне джерело часу, і ``created_at`` /
    ``updated_at`` можна перевірити точно.

    Увага: сесія закінчується після 30 хв бездіяльності, тож перемотуйте
    час кроками, коротшими за 30 хв.
    """
    return env.clock


# File was created by Claude. Reviewed by Kozynska Anastasia
# Clock injection by Claude. Review pending: Kozynska Anastasia
