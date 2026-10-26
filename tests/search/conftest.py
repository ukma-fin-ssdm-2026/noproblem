"""Fixtures shared by search API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from tests.conftest import IamTestEnv


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    """Build the FastAPI stack for HTTP contract tests.

    Unlike service tests, these check HTTP status and query validation;
    IAM services come from env so sign_up can register a real test user.
    """
    return TestClient(create_app(iam=env.iam, access=env.access))
