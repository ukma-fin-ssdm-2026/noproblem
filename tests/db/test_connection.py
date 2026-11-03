"""Характеризаційні тести підключення до PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.db.connection import (
    DATABASE_URL_ENV,
    create_pool,
    database_url,
    load_env_file,
)


@pytest.mark.parametrize("value", ["", "   ", " \t\n"])
def test_database_url_is_none_for_empty_or_whitespace_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, value)

    assert database_url() is None


def test_load_env_file_does_not_override_existing_environment_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    variable = "NOTELY_CONNECTION_TEST_VALUE"
    env_file = tmp_path / ".env"
    env_file.write_text(f"{variable}=from-file\n", encoding="utf-8")
    monkeypatch.setenv(variable, "from-environment")

    assert load_env_file(env_file) is True
    assert os.environ[variable] == "from-environment"


def test_create_pool_can_remain_closed_with_default_sizes() -> None:
    pool = create_pool("postgresql://localhost/notely", open_immediately=False)
    try:
        assert pool.closed is True
        assert pool.min_size == 1
        assert pool.max_size == 10
    finally:
        pool.close()
