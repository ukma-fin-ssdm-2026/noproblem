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


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    """HTTP-клієнт до свіжого застосунку з ізольованим станом."""
    return TestClient(create_app(iam=env.iam, access=env.access))


# File was created by Claude. Reviewed by Kozynska Anastasia
