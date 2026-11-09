"""Fixtures for search reliability tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from tests.conftest import IamTestEnv


@pytest.fixture
def client(env: IamTestEnv) -> TestClient:
    """Build the in-memory API stack for HTTP reliability tests."""
    return TestClient(create_app(iam=env.iam, access=env.access))
